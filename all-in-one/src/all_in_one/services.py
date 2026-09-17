"""All-in-One services 注册表

聚合所有 service:
1. 初始化共享资源（DatabaseManager / RedisManager）
2. 根据 ENABLED_SERVICES 过滤，逐个调用各 service 的 setup() 完成路由注册
3. 返回 (services_registry, cleaner)
"""

import importlib
import traceback
from dataclasses import dataclass
from typing import Callable

from fastapi import FastAPI
from services_common.database import DatabaseManager
from services_common.idempotency import configure_idempotency
from services_common.logging import Logger
from services_common.redis import RedisManager
from services_common.resource_keys import DB_DEFAULT_KEY, REDIS_DEFAULT_KEY
from services_common.shared_resources import SharedResources

from all_in_one.config import Settings


# ──────────────────────────────────────────────────────────────────────────────
# Service 注册表 — 声明式，新增 service 只需加一行
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class ServiceEntry:
    """描述单个 service 的加载方式。"""
    name: str                       # service 标识（对应 ENABLED_SERVICES 里的值）
    setup_module: str               # setup() 所在模块路径
    settings_getter: str            # Settings 上获取该 service 配置的方法名
    required: bool = False          # required=True 时 setup 失败直接 raise


# 注册顺序即加载顺序
SERVICE_REGISTRY: list[ServiceEntry] = [
    ServiceEntry("pingpong-service",              "pingpong_service.main",              "get_pingpong_settings"),
    # 更多服务注册
    # ServiceEntry("xxxx-service",                "xxxxx_service.main",             "get_xxxxx_settings"),
]


# ──────────────────────────────────────────────────────────────────────────────
# 加载单个 service
# ──────────────────────────────────────────────────────────────────────────────

async def _load_service(
    entry: ServiceEntry,
    app: FastAPI,
    _settings: Settings,
    logger: Logger,
    shared_resources: SharedResources,
) -> tuple[str, Callable]:
    """加载单个 service，返回 (app_name, cleaner)。"""
    setup_mod = importlib.import_module(entry.setup_module)
    setup_fn = getattr(setup_mod, "setup")
    service_settings = getattr(_settings, entry.settings_getter)()

    cleaner = await setup_fn(app, service_settings, logger, shared_resources=shared_resources)
    return service_settings.APP_NAME, cleaner


# ──────────────────────────────────────────────────────────────────────────────
# 主注册流程
# ──────────────────────────────────────────────────────────────────────────────

def _parse_enabled_services(config: str) -> set[str] | None:
    """解析 ENABLED_SERVICES 配置，返回 None 表示全量加载。"""
    config = config.strip()
    if config == "*":
        return None
    return {s.strip() for s in config.split(",") if s.strip()}


async def services_registry(app: FastAPI, _settings: Settings, logger: Logger):
    """注册服务，返回 (services_registry, cleaner)。"""
    cleaner_list: list[Callable] = []
    _services_registry: dict[str, dict] = {}

    # ── 共享资源 ──
    shared_resources = SharedResources()
    shared_db_manager = None
    if _settings.ALL_IN_ONE_SHARE_DB:
        shared_db_manager = shared_resources.register(
            DB_DEFAULT_KEY,
            DatabaseManager(
                database_url=_settings.DATABASE_URL,
                pool_size=_settings.DB_POOL_SIZE,
                max_overflow=_settings.DB_MAX_OVERFLOW,
                echo=_settings.DB_ECHO,
            ),
            closer=lambda resource: resource.close(),
        )

    shared_redis_manager = None
    if _settings.ALL_IN_ONE_SHARE_REDIS:
        shared_redis_manager = shared_resources.register(
            REDIS_DEFAULT_KEY,
            RedisManager(
                redis_url=_settings.REDIS_URL,
                max_connections=_settings.REDIS_MAX_CONNECTIONS,
                decode_responses=_settings.REDIS_DECODE_RESPONSES,
                socket_timeout=_settings.REDIS_SOCKET_TIMEOUT,
                socket_connect_timeout=_settings.REDIS_SOCKET_CONNECT_TIMEOUT,
                health_check_interval=_settings.REDIS_HEALTH_CHECK_INTERVAL,
                retry_on_timeout=_settings.REDIS_RETRY_ON_TIMEOUT,
            ),
            closer=lambda resource: resource.close(),
        )

    logger.info(
        "All-in-one shared resources initialized",
        shared_db=shared_db_manager is not None,
        shared_redis=shared_redis_manager is not None,
    )

    # 幂等控制兜底注册：用共享 RedisManager 注册给 services_common.idempotency。
    # 各 service 的 setup() 也会自行 configure_idempotency(injector=...)；此处确保
    # 聚合进程内即使某 service 漏配，幂等装饰器仍能拿到共享 Redis（fail-open 不阻塞 API）。
    if shared_redis_manager is not None:
        configure_idempotency(redis_manager=shared_redis_manager, settings=_settings)

    # ── 解析 ENABLED_SERVICES ──
    enabled_set = _parse_enabled_services(_settings.ENABLED_SERVICES)
    if enabled_set is None:
        logger.info("ENABLED_SERVICES=* - All registered services will be loaded")
    else:
        logger.info(f"ENABLED_SERVICES configured: {', '.join(sorted(enabled_set))}")

    # ── 逐个加载 service ──
    loaded_names: set[str] = set()

    for entry in SERVICE_REGISTRY:
        # 在 setup() 之前过滤，避免未启用 service 的初始化副作用
        if enabled_set is not None and entry.name not in enabled_set:
            logger.info(f"Skipping {entry.name} (not in ENABLED_SERVICES)")
            continue

        try:
            app_name, cleaner = await _load_service(entry, app, _settings, logger, shared_resources)
            cleaner_list.append(cleaner)
            _services_registry[app_name] = {"enabled": True}
            loaded_names.add(entry.name)
            tag = " (required)" if entry.required else ""
            logger.info(f"Registered service: {entry.name}{tag}")
        except Exception as e:
            if entry.required:
                logger.error(f">>>>>>> Failed to load required {entry.name} exception: {e}")
                logger.error(f">>>>>>> Failed to load required {entry.name} stack: {traceback.format_exc()}")
                raise RuntimeError(f"required {entry.name} failed to initialize") from e
            else:
                logger.warning(f">>>>>>> Failed to load {entry.name} exception: {e}")
                logger.warning(f">>>>>>> Failed to load {entry.name} stack: {traceback.format_exc()}")

    # ── 汇总 ──
    logger.info(f"Loading {len(_services_registry)} services: {', '.join(_services_registry.keys())}")

    # ── 集中重建中间件栈 ──
    app.middleware_stack = app.build_middleware_stack()
    logger.info("All-in-one middleware stack rebuilt to capture per-service exception handlers")

    # 检查 ENABLED_SERVICES 中是否有无效名称
    if enabled_set is not None:
        invalid_services = enabled_set - loaded_names
        if invalid_services:
            logger.warning(
                f"Invalid service names in ENABLED_SERVICES (not registered): {', '.join(sorted(invalid_services))}"
            )

    # ── 清理 ──
    async def cleaner():
        try:
            for cl in cleaner_list:
                if callable(cl):
                    await cl()
            await shared_resources.close_all()
            logger.info(
                "All-in-one shared resources closed",
                shared_db=shared_db_manager is not None,
                shared_redis=shared_redis_manager is not None,
            )
        except Exception as e:
            logger.warning(f"Failed to cleaner: {e}")

    return _services_registry, cleaner
"""Worker-in-One workers 注册表

聚合所有 worker:
1. 初始化共享资源（DatabaseManager / RedisManager）
2. 根据 ENABLED_WORKERS 过滤，逐个调用各 worker 的 setup() 完成 DI 注入
3. 为每个 worker 产出一个 WorkerSpec（含 broker_type + handler 注册函数），
   交由 BrokerRunner 按中间件类型分组并发消费
"""

import importlib
import traceback
from dataclasses import dataclass
from typing import Callable

from workers_common.database import DatabaseManager
from workers_common.logging import Logger
from workers_common.redis import RedisManager
from workers_common.resource_keys import DB_DEFAULT_KEY, REDIS_DEFAULT_KEY
from workers_common.shared_resources import SharedResources

from worker_in_one.broker.spec import WorkerSpec
from worker_in_one.config import Settings


# ──────────────────────────────────────────────────────────────────────────────
# Worker 注册表 — 声明式，新增 worker 只需加一行
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class WorkerEntry:
    """描述单个 worker 的加载方式。"""
    name: str                           # worker 标识（对应 ENABLED_WORKERS 里的值）
    setup_module: str                   # setup() 所在模块路径
    handlers_module: str                # register_all_handlers 所在模块路径
    settings_getter: str                # Settings 上获取该 worker 配置的方法名
    required: bool = False              # required=True 时 setup 失败直接 raise


# 注册顺序即加载顺序；required worker 的失败会中断整个进程
WORKER_REGISTRY: list[WorkerEntry] = [
    WorkerEntry("pingpong-worker",      "pingpong_worker.main",      "pingpong_worker.handlers",      "get_pingpong_worker_settings"),
    # WorkerEntry("xxxx-worker",        "xxxx_worker.main",        "xxxx_worker.handlers",        "get_xxxx_worker_settings"),
]

# ──────────────────────────────────────────────────────────────────────────────
# 加载单个 worker
# ──────────────────────────────────────────────────────────────────────────────

async def _load_worker(
    entry: WorkerEntry,
    _settings: Settings,
    logger: Logger,
    shared_resources: SharedResources,
) -> tuple[WorkerSpec, Callable]:
    """加载单个 worker，返回 (WorkerSpec, cleaner)。"""
    # 延迟 import：未启用的 worker 不会触发其模块加载
    setup_mod = importlib.import_module(entry.setup_module)
    handlers_mod = importlib.import_module(entry.handlers_module)

    setup_fn = getattr(setup_mod, "setup")
    register_fn = getattr(handlers_mod, "register_all_handlers")
    worker_settings = getattr(_settings, entry.settings_getter)()

    cleaner = await setup_fn(worker_settings, logger, shared_resources=shared_resources)

    spec = WorkerSpec(
        name=entry.name,
        broker_type="celery",
        register_handlers=register_fn,
        settings=worker_settings,
        required=entry.required,
    )
    return spec, cleaner


# ──────────────────────────────────────────────────────────────────────────────
# 主注册流程
# ──────────────────────────────────────────────────────────────────────────────

def _parse_enabled_workers(config: str) -> set[str] | None:
    """解析 ENABLED_WORKERS 配置，返回 None 表示全量加载。"""
    config = config.strip()
    if config == "*":
        return None
    return {w.strip() for w in config.split(",") if w.strip()}


async def workers_registry(_settings: Settings, logger: Logger) -> tuple[list[WorkerSpec], Callable]:
    """注册所有 worker，返回 (worker_specs, cleaner)。"""
    cleaner_list: list[Callable] = []
    all_specs: list[WorkerSpec] = []

    # ── 共享资源 ──
    shared_resources = SharedResources()

    shared_db_manager = None
    if _settings.WORKER_IN_ONE_SHARE_DB:
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
    if _settings.WORKER_IN_ONE_SHARE_REDIS:
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
        "Worker-in-one shared resources initialized",
        shared_db=shared_db_manager is not None,
        shared_redis=shared_redis_manager is not None,
    )

    # ── 解析 ENABLED_WORKERS ──
    enabled_set = _parse_enabled_workers(_settings.ENABLED_WORKERS)
    if enabled_set is None:
        logger.info("ENABLED_WORKERS=* - All registered workers will be loaded")
    else:
        logger.info(f"ENABLED_WORKERS configured: {', '.join(sorted(enabled_set))}")

    # ── 逐个加载 worker ──
    for entry in WORKER_REGISTRY:
        # 在 setup() 之前过滤，避免未启用 worker 的初始化副作用
        if enabled_set is not None and entry.name not in enabled_set:
            logger.info(f"Skipping {entry.name} (not in ENABLED_WORKERS)")
            continue

        try:
            spec, cleaner = await _load_worker(entry, _settings, logger, shared_resources)
            cleaner_list.append(cleaner)
            all_specs.append(spec)
            tag = " (required)" if entry.required else ""
            logger.info(f"Registered worker: {entry.name}{tag}")
        except Exception as e:
            if entry.required:
                logger.error(f">>>>>>> Failed to load required {entry.name} exception: {e}")
                logger.error(f">>>>>>> Failed to load required {entry.name} stack: {traceback.format_exc()}")
                raise RuntimeError(f"required {entry.name} failed to initialize") from e
            else:
                logger.warning(f">>>>>>> Failed to load {entry.name} exception: {e}")
                logger.warning(f">>>>>>> Failed to load {entry.name} stack: {traceback.format_exc()}")

    # ── 汇总 ──
    specs = all_specs
    logger.info(f"Loading {len(specs)} workers: {', '.join([s.name for s in specs])}")

    # 检查 ENABLED_WORKERS 中是否有无效名称
    if enabled_set is not None:
        registered_names = {s.name for s in all_specs}
        invalid_workers = enabled_set - registered_names
        if invalid_workers:
            logger.warning(
                f"Invalid worker names in ENABLED_WORKERS (not registered): {', '.join(sorted(invalid_workers))}"
            )

    # ── 清理 ──
    async def cleaner():
        try:
            for cl in cleaner_list:
                if callable(cl):
                    await cl()
            await shared_resources.close_all()
            logger.info(
                "Worker-in-one shared resources closed",
                shared_db=shared_db_manager is not None,
                shared_redis=shared_redis_manager is not None,
            )
        except Exception as e:
            logger.warning(f"Failed to cleaner: {e}")

    return specs, cleaner
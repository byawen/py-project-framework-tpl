"""Worker-in-One workers 注册表

聚合所有 worker:
1. 初始化共享资源（DatabaseManager / RedisManager）
2. 逐个调用各 worker 的 setup() 完成 DI 注入
3. 为每个 worker 产出一个 WorkerSpec（含 broker_type + handler 注册函数），
   交由 BrokerRunner 按中间件类型分组并发消费
"""

import traceback
from typing import Callable

from workers_common.database import DatabaseManager
from workers_common.logging import Logger
from workers_common.redis import RedisManager
from workers_common.resource_keys import DB_DEFAULT_KEY, REDIS_DEFAULT_KEY
from workers_common.shared_resources import SharedResources

from worker_in_one.broker.spec import WorkerSpec
from worker_in_one.config import Settings


async def workers_registry(_settings: Settings, logger: Logger) -> tuple[list[WorkerSpec], Callable]:
    """注册所有 worker，返回 (worker_specs, cleaner)。"""
    cleaner_list = []
    specs: list[WorkerSpec] = []

    # ============================================
    # 共享资源
    # ============================================
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

    # ============================================
    # 加载 worker
    # ============================================

    try:
        from pingpong_worker.main import setup as pingpong_worker_setup
        from pingpong_worker.handlers import register_all_handlers as pingpong_register
        worker_settings = _settings.get_pingpong_worker_settings()
        cleaner = await pingpong_worker_setup(worker_settings, logger, shared_resources=shared_resources)
        cleaner_list.append(cleaner)
        specs.append(
            WorkerSpec(
                name="pingpong-worker",
                broker_type="celery",
                register_handlers=pingpong_register,
                settings=worker_settings,
            )
        )
        logger.info("Loaded worker: pingpong-worker")
    except Exception as e:
        logger.warning(f">>>>>>> Failed to load pingpong-worker exception: {e}")
        logger.warning(f">>>>>>> Failed to load pingpong-worker stack: {traceback.format_exc()}")

    # 新增 worker 在此添加:
    # try:
    #     from xxx_worker.main import setup as xxx_worker_setup
    #     from xxx_worker.handlers import register_all_handlers as xxx_register
    #     worker_settings = _settings.get_xxx_worker_settings()
    #     cleaner = await xxx_worker_setup(worker_settings, logger, shared_resources=shared_resources)
    #     cleaner_list.append(cleaner)
    #     specs.append(
    #         WorkerSpec(
    #             name="xxx-worker",
    #             broker_type="celery",
    #             register_handlers=xxx_register,
    #             settings=worker_settings,
    #         )
    #     )
    #     logger.info("Loaded worker: xxx-worker")
    # except Exception as e:
    #     logger.warning(f">>>>>>> Failed to load xxx-worker exception: {e}")
    #     logger.warning(f">>>>>>> Failed to load xxx-worker stack: {traceback.format_exc()}")

    # ============================================
    # 清理
    # ============================================
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

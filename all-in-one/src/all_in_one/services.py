import traceback

from fastapi import FastAPI
from services_common.database import DatabaseManager
from services_common.logging import Logger
from services_common.redis import RedisManager
from services_common.resource_keys import DB_DEFAULT_KEY, REDIS_DEFAULT_KEY
from services_common.shared_resources import SharedResources

from all_in_one.config import Settings

async def services_registry(app: FastAPI, _settings: Settings, logger: Logger):
    """注册服务"""
    cleaner_list = []
    _services_registry = {}

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

    # ============================================
    # 加载服务
    # ============================================
    try:
        from pingpong_service.main import setup as pingpong_setup
        service_settings = _settings.get_pingpong_settings()
        cleaner = await pingpong_setup(app, service_settings, logger, shared_resources=shared_resources)
        cleaner_list.append(cleaner)
        _services_registry[service_settings.APP_NAME] = {"enabled": True}
    except Exception as e:
        logger.warning(f">>>>>>> Failed to load pingpong-service exception: {e}")
        logger.warning(f">>>>>>> Failed to load pingpong-service stack: {traceback.format_exc()}")

    # 新增 service 在此添加:
    # try:
    #     from xxx_service.main import setup as xxx_setup
    #     service_settings = _settings.get_xxx_settings()
    #     cleaner = await xxx_setup(app, service_settings, logger, shared_resources=shared_resources)
    #     cleaner_list.append(cleaner)
    #     _services_registry[service_settings.APP_NAME] = {"enabled": True}
    # except Exception as e:
    #     logger.warning(f">>>>>>> Failed to load xxx-service exception: {e}")
    #     logger.warning(f">>>>>>> Failed to load xxx-service stack: {traceback.format_exc()}")

    # 退出清理
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

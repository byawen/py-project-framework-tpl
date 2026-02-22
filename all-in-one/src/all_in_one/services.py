from fastapi import FastAPI
from services_common.logging import Logger
from all_in_one.config import Settings

async def services_registry(app: FastAPI, _settings: Settings, logger: Logger):
    """注册服务"""
    cleaner_list = []
    _services_registry = {}

    # ============================================
    # 加载服务
    # ============================================
    try:
        from pingpong_service.main import setup as pingpong_setup
        service_settings = _settings.get_pingpong_settings()
        cleaner = await pingpong_setup(app, service_settings, logger)
        cleaner_list.append(cleaner)
        _services_registry[service_settings.APP_NAME] = {"enabled": True}
    except Exception as e:
        logger.warning(f">>>>>>> Failed to load pingpong-service: {e}")

    # ...

    # 退出清理
    async def cleaner():
        try:
            for cl in cleaner_list:
                if callable(cl):
                    await cl()
                logger.info("Database connection closed")
        except Exception as e:
            logger.warning(f"Failed to cleaner: {e}")

    return _services_registry, cleaner
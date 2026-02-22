"""PingPong 服务主入口"""

from contextlib import asynccontextmanager
from typing import Callable, Any, Coroutine

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from injector import Injector, Module, Binder
from sqlalchemy.ext.asyncio.engine import AsyncEngine
from sqlalchemy.ext.asyncio import AsyncSession

from services_common import configure_uvicorn_logging
from services_common.database import DatabaseManager
from services_common.redis import RedisManager
from services_common.middleware import RequestIDMiddleware
from services_common.logging import Logger

from pingpong_service.foundation.logging import LogManager
from pingpong_service.foundation.config import Settings
from pingpong_service.app.api.v1 import api_router
from pingpong_service.foundation.exception_handlers import register_exception_handlers
from pingpong_service.foundation.logging import get_logger
from pingpong_service.foundation.container import set_injector

from pingpong_service.clients.modules import ClientsModule
from pingpong_service.app.domain.modules import DomainModule
from pingpong_service.app.application.modules import ApplicationModule
from pingpong_service.app.infrastructure.modules import InfrastructureModule

async def setup(_app: FastAPI, _settings: Settings, logger: Logger, api_prefix="/api") -> Callable[
    [], Coroutine[Any, Any, None]]:
    """初始化，需要注意 all-in-one 模式共用"""
    if not logger:
        logger = get_logger(__name__)

    # API Router (router already has /v1 prefix)
    _app.include_router(api_router, prefix=api_prefix)

    # Middleware
    # app.add_middleware(RequestAPIKeyMiddleware)

    # 使用 DatabaseManager 管理数据库连接
    _db_manager = DatabaseManager(
        database_url=_settings.DATABASE_URL,
        pool_size=_settings.DB_POOL_SIZE,
        max_overflow=_settings.DB_MAX_OVERFLOW,
        echo=_settings.DB_ECHO,
    )

    # 使用 RedisManager 管理 Redis 连接
    _redis_manager = RedisManager(
        redis_url=_settings.REDIS_URL,
        max_connections=_settings.REDIS_MAX_CONNECTIONS,
        decode_responses=True,
    )

    class BuiltinModule(Module):
        """预置基础模块的依赖注入"""

        def configure(self, binder: Binder):
            binder.bind(Settings, to=lambda: _settings, scope=None)
            binder.bind(RedisManager, to=lambda: _redis_manager, scope=None)
            binder.bind(DatabaseManager, to=lambda: _db_manager, scope=None)
            binder.bind(AsyncEngine, to=lambda: _db_manager.engine, scope=None)
            binder.bind(AsyncSession, to=lambda: _db_manager.session_maker, scope=None)
            binder.bind(LogManager, to=LogManager, scope=None)

    # 创建 Injector
    _injector = Injector([BuiltinModule, ClientsModule, DomainModule, ApplicationModule, InfrastructureModule])

    # # 手动绑定注入
    # _injector.binder.bind(Xxxx, to=Xxxx, scope=None)

    # 设置全局 Injector
    set_injector(_injector)

    async def cleaner():
        await _redis_manager.close()
        logger.info("Redis connection closed")

        await _db_manager.close()
        logger.info("Database connection closed")

    return cleaner


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """应用生命周期管理器"""
    # 使用新的日志系统
    logger = get_logger(__name__)
    logger.info("Starting pingpong Service...")

    # 结构化输出 uvicorn 日志
    configure_uvicorn_logging()

    # Startup: 初始化数据库连接池
    _settings: Settings = _app.state.settings

    cleaner = await setup(_app, _settings, logger, "/api")

    logger.info("Database and Redis connections initialized")
    logger.info("Injector configured")
    
    yield
    
    # Shutdown: 清理资源
    logger.info("Shutting down pingpong Service...")

    await cleaner()


def create_app(_settings: Settings = None) -> FastAPI:
    """创建并配置 FastAPI 应用"""
    if _settings is None:
        from pingpong_service.foundation.config import get_settings
        _settings = get_settings()
    
    app = FastAPI(
        title="Ping Pong Service",
        description="Ping Pong 认证和管理服务",
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    
    # Store settings in app state
    app.state.settings = _settings
    
    # Middleware
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Exception handlers
    register_exception_handlers(app)

    # Health check
    @app.get("/health")
    async def health_check():
        return {
            "status": "healthy",
            "service": "pingpong-service",
            "version": "2.0.0",
        }
    
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    from pingpong_service.foundation.config import get_settings
    settings = get_settings()
    
    uvicorn.run(
        "pingpong_service.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )

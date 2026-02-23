"""All-in-One 应用入口模块

此模块将所有微服务组合成一个 FastAPI 应用。
每个服务保持自己的 DI 模块，但共享基础设施（数据库、Redis）。
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from injector import Injector, Module, Binder
from sqlalchemy.ext.asyncio.engine import AsyncEngine
from sqlalchemy.ext.asyncio import AsyncSession

from all_in_one.foundation.exception_handlers import register_exception_handlers
from all_in_one.services import services_registry
from services_common import configure_uvicorn_logging
from services_common.database import DatabaseManager
from services_common.redis import RedisManager
from services_common.middleware import RequestIDMiddleware, ErrorHandlingMiddleware
from services_common.logging import Logger

from all_in_one.foundation.container import set_injector
from all_in_one.config import Settings, get_settings
from all_in_one.foundation.logging import LogManager, get_logger

# 服务注册表
_services_registry = {}

async def setup(app: FastAPI, _settings: Settings, logger: Logger):
    """初始化"""
    if not logger:
        logger = get_logger(__name__)

    # Middleware
    # app.add_middleware(RequestAPIKeyMiddleware)

    _services_registry, cleaner = await services_registry(app, _settings, logger)
    return cleaner


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期 - 启动和关闭"""
    logger = get_logger(__name__)
    logger.info("Starting Services- All-in-One Mode...")
    
    # 配置 JSON 日志
    configure_uvicorn_logging()

    # 初始化配置
    _settings: Settings = app.state.settings
    
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
    
    # 内置模块 - 共享基础设施
    class BuiltinModule(Module):
        """共享基础设施模块"""
        def configure(self, binder: Binder):
            binder.bind(Settings, to=lambda: _settings, scope=None)
            binder.bind(RedisManager, to=lambda: _redis_manager, scope=None)
            binder.bind(DatabaseManager, to=lambda: _db_manager, scope=None)
            binder.bind(AsyncEngine, to=lambda: _db_manager.engine, scope=None)
            binder.bind(AsyncSession, to=lambda: _db_manager.session_maker, scope=None)
            binder.bind(LogManager, to=LogManager, scope=None)
    
    # 创建注入器，包含所有服务模块
    injector_modules = [BuiltinModule]
    
    # 创建并设置注入器
    _injector = Injector(injector_modules)

    # # 手动绑定注入
    # _injector.binder.bind(Xxxx, to=Xxxx, scope=None)

    # 设置全局 Injector
    set_injector(_injector)

    # 初始化
    cleaner = await setup(app, _settings, logger)
    
    logger.info("All-in-One infrastructure initialized")
    
    yield
    
    # 关闭
    logger.info("Shutting down Services - All-in-One Mode...")
    
    await _redis_manager.close()
    await _db_manager.close()

    # 清除
    if cleaner:
        await cleaner()


def create_app(_settings: Settings = None) -> FastAPI:
    """创建并配置 FastAPI 应用"""
    if _settings is None:
        _settings = get_settings()

    app = FastAPI(
        title="All-in-One",
        description="All microservices combined into a single application",
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    
    # 存储配置
    app.state.settings = _settings

    # Middleware - 最后添加的最先执行，所以 ErrorHandlingMiddleware 要放在最前面
    # 执行顺序: ErrorHandling -> RequestID -> CORS -> 路由
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(ErrorHandlingMiddleware)

    # Exception handlers
    register_exception_handlers(app)
    
    # 健康检查
    @app.get("/health")
    async def health_check():
        return {
            "status": "healthy",
            "mode": "all-in-one",
            "version": "2.0.0",
            "services": [k for k, v in _services_registry.items() if v["enabled"]],
        }

    return app


# 创建应用实例
app = create_app()


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )

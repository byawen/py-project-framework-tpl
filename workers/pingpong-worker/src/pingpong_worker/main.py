"""PingPong Worker 主入口"""

import asyncio
from typing import Callable, Any, Coroutine

from injector import Injector, Module, Binder
from sqlalchemy.ext.asyncio.engine import AsyncEngine
from sqlalchemy.ext.asyncio import AsyncSession

from workers_common.database import DatabaseManager
from workers_common.redis import RedisManager
from workers_common.shared_resources import SharedResources
from workers_common.logging import Logger, configure_logging, shutdown_file_logging

from pingpong_worker.foundation.logging import LogManager
from pingpong_worker.foundation.config import Settings
from pingpong_worker.foundation.container import set_injector

from pingpong_worker.clients.modules import ClientsModule
from pingpong_worker.app.domain.modules import DomainModule
from pingpong_worker.app.application.modules import ApplicationModule
from pingpong_worker.app.infrastructure.modules import InfrastructureModule


async def setup(
    _settings: Settings,
    logger: Logger,
    shared_resources: SharedResources | None = None,
) -> Callable[[], Coroutine[Any, Any, None]]:
    """初始化，需要注意 all-in-one 模式共用"""
    if not logger:
        from pingpong_worker.foundation.logging import get_logger

        logger = get_logger(__name__)

    owns_db_manager = shared_resources is None or shared_resources.get_db() is None
    _db_manager = shared_resources.get_db() if shared_resources else None
    if _db_manager is None:
        _db_manager = DatabaseManager(
            database_url=_settings.DATABASE_URL,
            pool_size=_settings.DB_POOL_SIZE,
            max_overflow=_settings.DB_MAX_OVERFLOW,
            echo=_settings.DB_ECHO,
        )

    owns_redis_manager = shared_resources is None or shared_resources.get_redis() is None
    _redis_manager = shared_resources.get_redis() if shared_resources else None
    if _redis_manager is None:
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
    _injector = Injector(
        [BuiltinModule, ClientsModule, DomainModule, ApplicationModule, InfrastructureModule]
    )

    # 设置全局 Injector
    set_injector(_injector)

    if owns_redis_manager:
        logger.info(f"Redis connections initialized, worker: {_settings.APP_NAME}")
    if owns_db_manager:
        logger.info(f"Database connections initialized, worker: {_settings.APP_NAME}")
    logger.info(f"Worker initialized, worker: {_settings.APP_NAME}")

    async def cleaner():
        if owns_redis_manager:
            await _redis_manager.close()
            logger.info(f"Redis connection closed, worker: {_settings.APP_NAME}")

        if owns_db_manager:
            await _db_manager.close()
            logger.info(f"Database connection closed, worker: {_settings.APP_NAME}")

    return cleaner


def run_worker():
    """启动 Worker 入口"""
    from pingpong_worker.foundation.config import get_settings

    _settings = get_settings()

    configure_logging(
        service_name=_settings.APP_NAME,
        log_dir=_settings.LOG_DIR,
        log_level=_settings.LOG_LEVEL,
        log_console=_settings.LOG_CONSOLE,
        log_file=_settings.LOG_FILE,
        log_file_max_bytes=_settings.LOG_FILE_MAX_BYTES,
        log_file_backup_count=_settings.LOG_FILE_BACKUP_COUNT,
    )

    from pingpong_worker.foundation.logging import get_logger

    logger = get_logger(__name__)
    logger.info("Starting pingpong Worker...")

    # 装配 DI 容器（Redis + DB + clients/application/infra）
    # 必须在 start_all() 之前完成，否则 handler 内 get_injector() 会返回未初始化
    asyncio.run(setup(_settings, logger))

    # 获取 broker manager 并启动消费
    from workers_common.broker import BrokerManager

    # 用 worker 专有前缀字段覆盖公共 CELERY_* 字段
    _settings.CELERY_TASK_DEFAULT_QUEUE = _settings.PIPO_CELERY_TASK_DEFAULT_QUEUE
    _settings.CELERY_TASK_ROUTES = _settings.PIPO_CELERY_TASK_ROUTES
    _settings.CELERY_TASK_QUEUES = _settings.PIPO_CELERY_TASK_QUEUES
    _settings.CELERY_BEAT_ENABLE = _settings.PIPO_CELERY_BEAT_ENABLE
    _settings.CELERY_BEAT_SCHEDULE = _settings.PIPO_CELERY_BEAT_SCHEDULE
    _settings.CELERY_BEAT_SCHEDULE_FILENAME = _settings.PIPO_CELERY_BEAT_SCHEDULE_FILENAME

    manager = BrokerManager()
    manager.register("celery", _settings)
    logger.info(
        "BrokerManager initialized",
        brokers=manager.registered_names,
    )

    # start_all() 内部自动完成：
    #   1. handler 注册（从 pingpong_worker.handlers.register_all_handlers）
    #   2. beat schedule 注入（若 CELERY_BEAT_ENABLE=True 且 schedule 非空）
    #   3. queue 列表派生（从 TASK_ROUTES）
    #   4. 启动 celery worker（含 --beat flag）
    # 多节点幂等由各 handler 内 Redis 分布式锁保证
    logger.info(
        "Starting Celery worker (beat=%s)",
        _settings.CELERY_BEAT_ENABLE and bool(_settings.CELERY_BEAT_SCHEDULE),
    )
    manager.start_all()


if __name__ == "__main__":
    run_worker()

"""PingPong Worker 主入口"""

import asyncio
from typing import Callable, Any, Coroutine

from injector import Injector, Module, Binder

from workers_common import thread_resources as _thread_resources
from workers_common.async_bridge import dispose_thread_loop, install_shutdown_hook
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

    # ── 资源访问器（thread-local）──────────────────────
    # DatabaseManager / RedisManager 不再绑成进程级单例。在 --pool=threads 下，
    # 单例 manager 的连接池会绑定到首个工作线程的 loop，其余线程复用即跨 loop 崩
    # 改为每工作线程惰性创建一份，池绑本线程 loop —— thread-local 在 prefork 下
    # 退化为「每进程一份」，无回归。因此统一用访问器，忽略 shared_resources 传入
    # 的进程级共享 manager（共享 manager 是为 prefork 单例设计，threads 下不安全）。
    def _db_provider():
        return _thread_resources.get_or_create_db_manager(_settings)

    def _redis_provider():
        return _thread_resources.get_or_create_redis_manager(_settings)

    class BuiltinModule(Module):
        """预置基础模块的依赖注入"""

        def configure(self, binder: Binder):
            binder.bind(Settings, to=lambda: _settings, scope=None)
            # scope=None：每次 injector.get 都走 provider → 取当前线程的 manager
            from workers_common.database import DatabaseManager
            from workers_common.redis import RedisManager

            binder.bind(DatabaseManager, to=_db_provider, scope=None)
            binder.bind(RedisManager, to=_redis_provider, scope=None)
            binder.bind(LogManager, to=LogManager, scope=None)

    # 创建 Injector
    _injector = Injector(
        [BuiltinModule, ClientsModule, DomainModule, ApplicationModule, InfrastructureModule]
    )

    # 设置全局 Injector
    set_injector(_injector)

    # 注册 async_bridge 进程级钩子（standalone 模式覆盖；worker-in-one 模式下队列子进程
    # 也会再注册一次，幂等）。
    install_shutdown_hook()

    logger.info(f"Worker initialized (thread-local resources), worker: {_settings.APP_NAME}")

    async def cleaner():
        # 关闭当前线程（主线程）惰性创建的资源；工作线程的 loop/资源由各自进程的
        # async_bridge shutdown 钩子在进程退出时释放。best-effort，不抛错。
        try:
            dispose_thread_loop()
            logger.info(f"Thread-local resources disposed, worker: {_settings.APP_NAME}")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Failed to dispose thread-local resources: {exc}")

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

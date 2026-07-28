from injector import Module, Binder, singleton, inject

from pingpong_service.foundation.config import Settings
from services_common.task_publisher import TaskPublisherManager


@inject
def _create_task_publisher_manager(settings: Settings) -> TaskPublisherManager:
    """显式注册 publisher — 当前只使用 celery"""
    # 用服务专有路由覆盖公共默认值（CeleryTaskPublisher 通过 getattr 读 CELERY_*）
    settings.CELERY_ACCEPT_CONTENT = settings.PIPO_CELERY_ACCEPT_CONTENT
    settings.CELERY_TASK_ROUTES = settings.PIPO_CELERY_TASK_ROUTES
    manager = TaskPublisherManager()
    manager.register("celery", settings)
    return manager


class InfrastructureModule(Module):
    """模块的依赖注入"""
    def configure(self, binder: Binder):
        # Cache
        from pingpong_service.app.domain.caches.pp_cache import PPCache
        from pingpong_service.app.infrastructure.caches.pp_redis_cache import PPRedisCache
        binder.bind(PPCache, to=PPRedisCache, scope=None)

        # Repository
        from pingpong_service.app.domain.repositories.ping_repository import PingRepository
        from pingpong_service.app.infrastructure.persistence.repositories.sql_ping_repository import SQLPingRepository
        binder.bind(PingRepository, to=SQLPingRepository, scope=None)

        from pingpong_service.app.domain.repositories.pong_repository import PongRepository
        from pingpong_service.app.infrastructure.persistence.repositories.sql_pong_repository import SQLPongRepository
        binder.bind(PongRepository, to=SQLPongRepository, scope=None)

        # Task Publisher + Dispatcher（向 pingpong-worker 投递异步任务）
        # TaskPublisherManager 用 callable provider 懒构造（首次被 Dispatcher 注入时才 register celery）
        binder.bind(TaskPublisherManager, to=_create_task_publisher_manager, scope=singleton)
        from pingpong_service.app.infrastructure.task_dispatcher import EchoTaskDispatcher
        binder.bind(EchoTaskDispatcher, scope=singleton)
from injector import Module, Binder


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
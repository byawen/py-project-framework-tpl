from injector import Module, Binder


class ApplicationModule(Module):
    """模块的依赖注入"""
    def configure(self, binder: Binder):
        from pingpong_service.app.application.commands import PongCommand
        binder.bind(PongCommand, to=PongCommand, scope=None)

        from pingpong_service.app.application.queries import PingQuery
        binder.bind(PingQuery, to=PingQuery, scope=None)

        from pingpong_service.app.application.queries import BizCodeTestQuery
        binder.bind(BizCodeTestQuery, to=BizCodeTestQuery, scope=None)

        # Service
        from pingpong_service.app.application.services.pp_service import PPService
        binder.bind(PPService, to=PPService, scope=None)
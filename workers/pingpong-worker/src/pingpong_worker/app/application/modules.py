from injector import Module, Binder


class ApplicationModule(Module):
    """模块的依赖注入"""

    def configure(self, binder: Binder):
        # Service
        from pingpong_worker.app.application.services.pp_service import PPService

        binder.bind(PPService, to=PPService, scope=None)

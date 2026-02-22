from injector import Module, Binder


class ClientsModule(Module):
    """模块的依赖注入"""
    def configure(self, binder: Binder):
        from pingpong_service.clients.github import GithubOauthAPIClient
        binder.bind(GithubOauthAPIClient, to=GithubOauthAPIClient, scope=None)

        from pingpong_service.clients.other_service import OtherServiceAPIProxy
        binder.bind(OtherServiceAPIProxy, to=OtherServiceAPIProxy, scope=None)

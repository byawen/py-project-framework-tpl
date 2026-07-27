from injector import Module, Binder


class ClientsModule(Module):
    """模块的依赖注入"""

    def configure(self, binder: Binder):
        from pingpong_worker.clients.github.oauth import GithubOauthAPIClient

        binder.bind(GithubOauthAPIClient, to=GithubOauthAPIClient, scope=None)

        from pingpong_worker.clients.other_service.api_proxy import OtherServiceAPIProxy

        binder.bind(OtherServiceAPIProxy, to=OtherServiceAPIProxy, scope=None)

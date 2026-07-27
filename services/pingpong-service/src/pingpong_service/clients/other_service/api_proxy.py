from injector import inject

from pingpong_service.clients.other_service.interface import UserService
from pingpong_service.foundation.config import Settings

class OtherServiceAPIProxy(UserService):
    """Other Service API 客户端"""
    @inject
    def  __init__(self, setting: Settings):
        self.proxy: UserService
        if setting.MODEL == "all-in-one":
            from pingpong_service.clients.other_service.local_api import LocalUserService
            self.proxy = LocalUserService()
        else:
            from pingpong_service.clients.other_service.remote_api import RemoteUserService
            self.proxy = RemoteUserService(base_url=setting.OTHER_SERVICE_URL or "http://127.0.0.1:8001")

    async def get_user_by_id(self, user_id: str):
        res = await self.proxy.get_user_by_id(user_id)
        return res

    async def update_user_name(self, user_id: str, name: str) -> None:
        await self.proxy.update_user_name(user_id, name)
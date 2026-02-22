from httpx import AsyncClient
from pingpong_service.clients.other_service.interface import UserService
from pingpong_service.clients.other_service.schemas import UserInfo

class RemoteUserService(UserService):
    """ Standalone 模式下远程服务API"""
    def __init__(self, base_url: str):
        self.client = AsyncClient(base_url=base_url)

    async def get_user_by_id(self, user_id: str) -> UserInfo:
        # resp = await self.client.get(f"/users/{user_id}")
        # resp.raise_for_status()
        # return UserInfo(**resp.json())
        return UserInfo(id="test", name="test")

    async def update_user_name(self, user_id: str, name: str) -> None:
        await self.client.patch(f"/users/{user_id}", json={"name": name})
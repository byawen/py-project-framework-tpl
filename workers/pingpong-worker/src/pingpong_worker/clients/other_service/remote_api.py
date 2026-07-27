"""Remote API 实现 — 微服务模式下通过 HTTP 调用"""

import httpx
from pingpong_worker.clients.other_service.interface import UserService
from pingpong_worker.clients.other_service.schemas import UserInfo


class RemoteUserService(UserService):
    """远程用户服务实现"""

    def __init__(self, base_url: str):
        self.base_url = base_url

    async def get_user_by_id(self, user_id: str) -> UserInfo:
        async with httpx.AsyncClient(base_url=self.base_url) as client:
            response = await client.get(f"/api/v1/users/{user_id}")
            data = response.json().get("data", {})
            return UserInfo(**data)

    async def update_user_name(self, user_id: str, name: str) -> None:
        async with httpx.AsyncClient(base_url=self.base_url) as client:
            await client.patch(f"/api/v1/users/{user_id}", json={"name": name})

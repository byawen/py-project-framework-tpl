from httpx import AsyncClient
from pingpong_service.clients.other_service.interface import UserService
from pingpong_service.clients.other_service.schemas import UserInfo
from pingpong_service.foundation.logging import get_logger

logger = get_logger(__name__)

class RemoteUserService(UserService):
    """ Standalone 模式下远程服务API"""
    def __init__(self, base_url: str):
        self.client = AsyncClient(base_url=base_url)

    async def get_user_by_id(self, user_id: str) -> UserInfo:
        logger.info(
            "调用远程用户服务查询用户",
            operation="pingpong.client.user.get_by_id",
            user_id=user_id,
        )
        # resp = await self.client.get(f"/users/{user_id}")
        # resp.raise_for_status()
        # return UserInfo(**resp.json())
        result = UserInfo(id="test", name="test")
        logger.info(
            "调用远程用户服务查询用户完成",
            operation="pingpong.client.user.get_by_id.success",
            user_id=user_id,
            found=True,
        )
        return result

    async def update_user_name(self, user_id: str, name: str) -> None:
        logger.info(
            "调用远程用户服务更新用户名",
            operation="pingpong.client.user.update_name",
            user_id=user_id,
            name=name,
        )
        await self.client.patch(f"/users/{user_id}", json={"name": name})
from pingpong_service.clients.other_service.interface import UserService
from pingpong_service.clients.other_service.schemas import UserInfo

class LocalUserService(UserService):
    """ All-In-One 模式下本地服务API"""
    def __init__(self):
        self._local_service = None

    @property
    def local_service(self):
        if self._local_service is None:
            # Example: pingpong service
            from pingpong_service.foundation.container import get_injector
            from pingpong_service.app.application.services import PPService
            self._local_service: PPService = get_injector().get(PPService)

        return self._local_service

    async def get_user_by_id(self, user_id: str) -> UserInfo:
        # user = await self.local_service.get_ping(user_id)
        user  = UserInfo(id="test", name="test")
        return UserInfo(id=user.id, name=user.name, email=user.email)

    async def update_user_name(self, user_id: str, name: str) -> None:
        await self.local_service.update_user_name(user_id, name)
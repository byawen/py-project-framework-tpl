from abc import ABC, abstractmethod

from pingpong_service.clients.other_service.schemas import UserInfo

class UserService(ABC):
    @abstractmethod
    async def get_user_by_id(self, user_id: str) -> UserInfo:
        pass

    @abstractmethod
    async def update_user_name(self, user_id: str, name: str) -> None:
        pass
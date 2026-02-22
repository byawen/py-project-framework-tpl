from pingpong_service.clients.other_service.interface import UserService
from pingpong_service.clients.other_service.schemas import UserInfo
from pingpong_service.clients.other_service.api_proxy import OtherServiceAPIProxy

__all__ = ["UserService", "UserInfo", "OtherServiceAPIProxy"]
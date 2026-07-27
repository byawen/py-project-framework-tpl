"""Application Layer Exceptions

应用层业务异常 - 从 services_common 继承
每个异常都绑定 BizCode 枚举成员，确保对外响应携带精确定位的业务码。
"""
from services_common.exceptions import (
    BaseApplicationException,
    AuthenticationFailedException,
    TokenExpiredException,
    TokenBlacklistedException,
)

from pingpong_service.foundation.biz_code import BizCode


class RegistrationFailedException(BaseApplicationException):
    """注册失败 - 用户名已占用或注册流程中校验不通过"""

    def __init__(self, reason: str):
        super().__init__(
            f"Registration failed: {reason}",
            code="REGISTRATION_FAILED",
            biz_code=BizCode.REGISTRATION_FAILED,
        )


class PasswordResetFailedException(BaseApplicationException):
    """密码重置失败 - 旧密码不匹配或重置令牌已失效"""

    def __init__(self, reason: str):
        super().__init__(
            f"Password reset failed: {reason}",
            code="PASSWORD_RESET_FAILED",
            biz_code=BizCode.PASSWORD_RESET_FAILED,
        )


# 重新导出通用异常
__all__ = [
    "AuthenticationFailedException",
    "TokenExpiredException",
    "TokenBlacklistedException",
    "RegistrationFailedException",
    "PasswordResetFailedException",
]
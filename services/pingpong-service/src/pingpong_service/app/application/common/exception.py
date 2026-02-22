"""Application Layer Exceptions

应用层业务异常 - 从 services_common 继承
"""
from services_common.exceptions import (
    BaseApplicationException,
    AuthenticationFailedException,
    TokenExpiredException,
    TokenBlacklistedException,
)

class RegistrationFailedException(BaseApplicationException):
    """Registration failed exception"""
    def __init__(self, reason: str):
        super().__init__(f"Registration failed: {reason}", code="REGISTRATION_FAILED")


class PasswordResetFailedException(BaseApplicationException):
    """Password reset failed exception"""
    def __init__(self, reason: str):
        super().__init__(f"Password reset failed: {reason}", code="PASSWORD_RESET_FAILED")


# 重新导出通用异常
__all__ = [
    "AuthenticationFailedException",
    "TokenExpiredException",
    "TokenBlacklistedException",
    "RegistrationFailedException",
    "PasswordResetFailedException",
]

"""Domain Exceptions

领域规则异常 - 从 workers_common 继承
"""

from workers_common.exceptions import (
    BaseDomainException,
    InvalidCredentialsException,
    InvalidTokenException,
    PasswordTooWeakException,
)


class PaPNotFoundException(BaseDomainException):
    """pap not found exception"""

    def __init__(self, p_id: str = None):
        message = f"pap not found: {p_id}" if p_id else "pap not found"
        super().__init__(message, code="PAP_NOT_FOUND")


class PaPAlreadyExistsException(BaseDomainException):
    """pap already exists exception"""

    def __init__(self, field: str, value: str):
        message = f"pap with {field} '{value}' already exists"
        super().__init__(message, code="PAP_ALREADY_EXISTS")


class PaPDisabledException(BaseDomainException):
    """PaP disabled exception"""

    def __init__(self):
        super().__init__("pap is disabled", code="PAP_DISABLED")


# 重新导出通用异常
__all__ = [
    "BaseDomainException",
    "PaPNotFoundException",
    "PaPAlreadyExistsException",
    "InvalidCredentialsException",
    "InvalidTokenException",
    "PaPDisabledException",
    "PasswordTooWeakException",
]

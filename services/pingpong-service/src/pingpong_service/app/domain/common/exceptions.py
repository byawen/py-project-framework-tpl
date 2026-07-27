"""Domain Exceptions

领域规则异常 - 从 services_common 继承
每个异常都绑定 BizCode 枚举成员，确保对外响应携带精确定位的业务码。
"""
from services_common.exceptions import (
    BaseDomainException,
    InvalidCredentialsException,
    InvalidTokenException,
    PasswordTooWeakException,
)

from pingpong_service.foundation.biz_code import BizCode


class PaPNotFoundException(BaseDomainException):
    """PingPong 记录不存在 - 查询的实体在数据库中未找到"""

    def __init__(self, p_id: str = None):
        message = f"pap not found: {p_id}" if p_id else "pap not found"
        super().__init__(message, code="PAP_NOT_FOUND", biz_code=BizCode.PAP_NOT_FOUND)


class PaPAlreadyExistsException(BaseDomainException):
    """PingPong 记录已存在 - 创建操作时唯一约束冲突"""

    def __init__(self, field: str, value: str):
        message = f"pap with {field} '{value}' already exists"
        super().__init__(message, code="PAP_ALREADY_EXISTS", biz_code=BizCode.PAP_ALREADY_EXISTS)


class PaPDisabledException(BaseDomainException):
    """PingPong 记录已被禁用 - 当前操作不允许在禁用状态的记录上执行"""

    def __init__(self):
        super().__init__("pap is disabled", code="PAP_DISABLED", biz_code=BizCode.PAP_DISABLED)


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
"""异常类模块 - 所有服务共享的异常类

每个异常都携带 biz_code 业务码，用于前端精确区分业务错误场景。
biz_code 由 services_common.biz_code 的工具函数生成，各服务在自己的
foundation/biz_code.py 中声明 SERVICE_CODE 并组合具体的 BizCode 枚举。

公共异常类使用 service_code=0（即 services_common 共享码段）作为兜底，
各服务应在自身领域代码中抛出带有正确 service_code 的异常。
"""

from http import HTTPStatus
from typing import Any, Optional

from services_common.biz_code import BizCategory, make_biz_code

# services_common 共享码段，用于公共异常的兜底
# 各服务自有异常应使用自身的 SERVICE_CODE
_COMMON_SERVICE_CODE = 0


class BaseException(Exception):
    """服务基础异常类

    Attributes:
        message: 人类可读的错误消息
        code: 内部错误标识字符串（用于日志，不直接暴露给前端）
        biz_code: 8位整数业务码（对外响应使用）
        payload: 对外响应的结构化业务数据（自动透传到响应体独立的 payload 字段，
            如 {"retry_after": 58}、{"max_size": 1048576}）；与 detail 分工独立、互不覆盖
        details: 内部上下文字典（仅供日志/调试，不对外暴露；保留以向后兼容）
        status_code: HTTP 状态码（默认 HTTPStatus.BAD_REQUEST；异常可覆盖如频控 TOO_MANY_REQUESTS、过大 REQUEST_ENTITY_TOO_LARGE）

    payload 与 detail 的分工（响应体两个独立字段）：
        - payload：业务结构化数据，面向前端，确定结构，由领域/应用异常透传写入
          ErrorResponse.payload（如 {"retry_after": 58}、{"max_size": 1048576}）。
        - detail：调试信息，面向排障，非确定结构，由 HTTPException/校验错误处理器写入
          ErrorResponse.detail；领域/应用异常不写 detail（保持 None）。
        二者由不同处理器互斥写入，互不覆盖。
    """

    # 默认 HTTP 状态码；子类可覆盖（如频控 TOO_MANY_REQUESTS、文件过大 REQUEST_ENTITY_TOO_LARGE）
    status_code: int = HTTPStatus.BAD_REQUEST

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        biz_code: Optional[int] = None,
        details: Optional[dict[str, Any]] = None,
        payload: Optional[dict[str, Any]] = None,
        status_code: Optional[int] = None,
    ):
        self.message = message
        self.code = code
        self.biz_code = biz_code or make_biz_code(_COMMON_SERVICE_CODE, BizCategory.SYSTEM, 0)
        self.details = details or {}
        self.payload = payload or None
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.message)


# =============================================================================
# 领域异常 - DDD 领域层
# =============================================================================
class BaseDomainException(BaseException):
    """领域基础异常类"""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        biz_code: Optional[int] = None,
        payload: Optional[dict[str, Any]] = None,
        status_code: Optional[int] = None,
    ):
        super().__init__(
            message=message,
            code=code or "DOMAIN_ERROR",
            biz_code=biz_code or make_biz_code(_COMMON_SERVICE_CODE, BizCategory.BUSINESS_RULE, 0),
            payload=payload,
            status_code=status_code,
        )


class InvalidCredentialsException(BaseDomainException):
    """无效凭证异常 - 用户名或密码错误"""

    def __init__(self):
        super().__init__(
            "Invalid username or password",
            code="INVALID_CREDENTIALS",
            biz_code=make_biz_code(_COMMON_SERVICE_CODE, BizCategory.AUTH, 1),
        )


class InvalidTokenException(BaseDomainException):
    """无效令牌异常 - token 格式非法或无法解析"""

    def __init__(self):
        super().__init__(
            "Invalid or expired token",
            code="INVALID_TOKEN",
            biz_code=make_biz_code(_COMMON_SERVICE_CODE, BizCategory.AUTH, 2),
        )


class PasswordTooWeakException(BaseDomainException):
    """密码强度不足异常 - 注册/修改密码时密码不满足复杂度要求"""

    def __init__(self):
        super().__init__(
            "Password is too weak",
            code="PASSWORD_TOO_WEAK",
            biz_code=make_biz_code(_COMMON_SERVICE_CODE, BizCategory.VALIDATION, 1),
        )


# =============================================================================
# 应用异常 - DDD 应用层
# =============================================================================
class BaseApplicationException(BaseException):
    """应用基础异常类"""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        biz_code: Optional[int] = None,
        payload: Optional[dict[str, Any]] = None,
        status_code: Optional[int] = None,
    ):
        super().__init__(
            message=message,
            code=code or "APPLICATION_ERROR",
            biz_code=biz_code or make_biz_code(_COMMON_SERVICE_CODE, BizCategory.BUSINESS_RULE, 1),
            payload=payload,
            status_code=status_code,
        )


class AuthenticationFailedException(BaseApplicationException):
    """认证失败异常 - 登录流程中身份验证未通过"""

    def __init__(self):
        super().__init__(
            "Authentication failed",
            code="AUTH_FAILED",
            biz_code=make_biz_code(_COMMON_SERVICE_CODE, BizCategory.AUTH, 3),
        )


class TokenExpiredException(BaseApplicationException):
    """令牌过期异常 - token 超过有效期"""

    def __init__(self):
        super().__init__(
            "Token has expired",
            code="TOKEN_EXPIRED",
            biz_code=make_biz_code(_COMMON_SERVICE_CODE, BizCategory.AUTH, 4),
        )


class TokenBlacklistedException(BaseApplicationException):
    """令牌已加入黑名单异常 - token 已被主动注销/拉黑"""

    def __init__(self):
        super().__init__(
            "Token has been blacklisted",
            code="TOKEN_BLACKLISTED",
            biz_code=make_biz_code(_COMMON_SERVICE_CODE, BizCategory.AUTH, 5),
        )


class NotFoundException(BaseException):
    """资源未找到异常 - 请求的实体在数据库中不存在"""
    
    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            message=f"{resource} with id {resource_id} not found",
            code="NOT_FOUND",
            biz_code=make_biz_code(_COMMON_SERVICE_CODE, BizCategory.NOT_FOUND, 0),
            details={"resource": resource, "resource_id": resource_id},
        )


class AlreadyExistsException(BaseException):
    """资源已存在异常 - 创建操作时唯一约束冲突"""
    
    def __init__(self, resource: str, identifier: str):
        super().__init__(
            message=f"{resource} with identifier {identifier} already exists",
            code="ALREADY_EXISTS",
            biz_code=make_biz_code(_COMMON_SERVICE_CODE, BizCategory.CONFLICT, 0),
            details={"resource": resource, "identifier": identifier},
        )


class UnauthorizedException(BaseException):
    """未授权异常 - 请求未携带有效认证信息"""
    
    def __init__(self, message: str = "Unauthorized"):
        super().__init__(
            message=message,
            code="UNAUTHORIZED",
            biz_code=make_biz_code(_COMMON_SERVICE_CODE, BizCategory.AUTH, 6),
        )


class ForbiddenException(BaseException):
    """禁止访问异常 - 认证通过但无权限访问该资源"""
    
    def __init__(self, message: str = "Forbidden"):
        super().__init__(
            message=message,
            code="FORBIDDEN",
            biz_code=make_biz_code(_COMMON_SERVICE_CODE, BizCategory.AUTH, 7),
        )


class ValidationException(BaseException):
    """验证异常 - 请求参数校验不通过"""
    
    def __init__(self, message: str, errors: Optional[list[dict]] = None):
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            biz_code=make_biz_code(_COMMON_SERVICE_CODE, BizCategory.VALIDATION, 0),
            details={"errors": errors or []},
        )


class RateLimitException(BaseException):
    """限流异常 - 请求频率超过阈值"""
    
    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(
            message=message,
            code="RATE_LIMIT_EXCEEDED",
            biz_code=make_biz_code(_COMMON_SERVICE_CODE, BizCategory.QUOTA, 0),
        )


class ServiceUnavailableException(BaseException):
    """服务不可用异常 - 下游依赖服务无法访问"""
    
    def __init__(self, service: str):
        super().__init__(
            message=f"Service {service} is unavailable",
            code="SERVICE_UNAVAILABLE",
            biz_code=make_biz_code(_COMMON_SERVICE_CODE, BizCategory.EXTERNAL, 0),
            details={"service": service},
        )
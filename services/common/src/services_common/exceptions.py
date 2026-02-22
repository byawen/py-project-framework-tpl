"""异常类模块 - 所有服务共享的异常类"""

from typing import Any, Optional
from fastapi import HTTPException, status


class BaseException(Exception):
    """服务基础异常类"""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        details: Optional[dict[str, Any]] = None,
    ):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)


# =============================================================================
# 领域异常 - DDD 领域层
# =============================================================================
class BaseDomainException(BaseException):
    """领域基础异常类"""

    def __init__(self, message: str, code: Optional[str] = None):
        super().__init__(
            message=message,
            code=code or "DOMAIN_ERROR",
        )


class InvalidCredentialsException(BaseDomainException):
    """无效凭证异常"""

    def __init__(self):
        super().__init__("Invalid username or password", code="INVALID_CREDENTIALS")


class InvalidTokenException(BaseDomainException):
    """无效令牌异常"""

    def __init__(self):
        super().__init__("Invalid or expired token", code="INVALID_TOKEN")


class PasswordTooWeakException(BaseDomainException):
    """密码强度不足异常"""

    def __init__(self):
        super().__init__("Password is too weak", code="PASSWORD_TOO_WEAK")


# =============================================================================
# 应用异常 - DDD 应用层
# =============================================================================
class BaseApplicationException(BaseException):
    """应用基础异常类"""

    def __init__(self, message: str, code: Optional[str] = None):
        super().__init__(
            message=message,
            code=code or "APPLICATION_ERROR",
        )


class AuthenticationFailedException(BaseApplicationException):
    """认证失败异常"""

    def __init__(self):
        super().__init__("Authentication failed", code="AUTH_FAILED")


class TokenExpiredException(BaseApplicationException):
    """令牌过期异常"""

    def __init__(self):
        super().__init__("Token has expired", code="TOKEN_EXPIRED")


class TokenBlacklistedException(BaseApplicationException):
    """令牌已加入黑名单异常"""

    def __init__(self):
        super().__init__("Token has been blacklisted", code="TOKEN_BLACKLISTED")


class NotFoundException(BaseException):
    """资源未找到异常"""
    
    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            message=f"{resource} with id {resource_id} not found",
            code="NOT_FOUND",
            details={"resource": resource, "resource_id": resource_id},
        )


class AlreadyExistsException(BaseException):
    """资源已存在异常"""
    
    def __init__(self, resource: str, identifier: str):
        super().__init__(
            message=f"{resource} with identifier {identifier} already exists",
            code="ALREADY_EXISTS",
            details={"resource": resource, "identifier": identifier},
        )


class UnauthorizedException(BaseException):
    """未授权异常"""
    
    def __init__(self, message: str = "Unauthorized"):
        super().__init__(
            message=message,
            code="UNAUTHORIZED",
        )


class ForbiddenException(BaseException):
    """禁止访问异常"""
    
    def __init__(self, message: str = "Forbidden"):
        super().__init__(
            message=message,
            code="FORBIDDEN",
        )


class ValidationException(BaseException):
    """验证异常"""
    
    def __init__(self, message: str, errors: Optional[list[dict]] = None):
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            details={"errors": errors or []},
        )


class RateLimitException(BaseException):
    """限流异常"""
    
    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(
            message=message,
            code="RATE_LIMIT_EXCEEDED",
        )


class ServiceUnavailableException(BaseException):
    """服务不可用异常"""
    
    def __init__(self, service: str):
        super().__init__(
            message=f"Service {service} is unavailable",
            code="SERVICE_UNAVAILABLE",
            details={"service": service},
        )

def http_exception_from_service_exception(exc: BaseException) -> HTTPException:
    """将服务异常转换为 FastAPI HTTPException"""
    status_code_map = {
        "NOT_FOUND": status.HTTP_404_NOT_FOUND,
        "ALREADY_EXISTS": status.HTTP_409_CONFLICT,
        "UNAUTHORIZED": status.HTTP_401_UNAUTHORIZED,
        "FORBIDDEN": status.HTTP_403_FORBIDDEN,
        "VALIDATION_ERROR": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "RATE_LIMIT_EXCEEDED": status.HTTP_429_TOO_MANY_REQUESTS,
        "SERVICE_UNAVAILABLE": status.HTTP_503_SERVICE_UNAVAILABLE,
        "LLM_ERROR": status.HTTP_502_BAD_GATEWAY,
        "AGENT_ERROR": status.HTTP_500_INTERNAL_SERVER_ERROR,
        "WORKFLOW_ERROR": status.HTTP_500_INTERNAL_SERVER_ERROR,
    }
    
    status_code = status_code_map.get(exc.code, status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    return HTTPException(
        status_code=status_code,
        detail={
            "message": exc.message,
            "code": exc.code,
            "details": exc.details,
        },
    )

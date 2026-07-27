"""异常类模块 - 所有 worker 共享的异常类"""

from typing import Any, Optional


class BaseException(Exception):
    """worker 基础异常类"""

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


class ValidationException(BaseException):
    """验证异常"""

    def __init__(self, message: str, errors: Optional[list[dict]] = None):
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            details={"errors": errors or []},
        )


class ServiceUnavailableException(BaseException):
    """服务不可用异常"""

    def __init__(self, service: str):
        super().__init__(
            message=f"Service {service} is unavailable",
            code="SERVICE_UNAVAILABLE",
            details={"service": service},
        )
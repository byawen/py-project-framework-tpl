"""Services Common Library - 所有服务共享的工具库"""

from services_common.logging import Logger, get_logger
from services_common.response import (
    ResponseCode,
    ResponseResult,
    DEFAULT_API_VERSION,
    BaseResponse,
    DataResponse,
    ListResponse,
    PageResponse,
    ErrorResponse,
    success,
    created,
    list_response,
    page_response,
    error,
    bad_request,
    unauthorized,
    forbidden,
    not_found,
    conflict,
)
from services_common.exceptions import (
    BaseException,
    BaseDomainException,
    BaseApplicationException,
    NotFoundException,
    AlreadyExistsException,
    UnauthorizedException,
    ForbiddenException,
    ValidationException,
    RateLimitException,
    ServiceUnavailableException,
    InvalidCredentialsException,
    InvalidTokenException,
    PasswordTooWeakException,
    AuthenticationFailedException,
    TokenExpiredException,
    TokenBlacklistedException,
)
from services_common.exception_handlers import register_base_exception_handlers
from services_common.uvicorn_logger import configure_uvicorn_logging
from services_common.database import BaseModel, DatabaseManager
from services_common.redis import RedisManager
from services_common.health import (
    HealthChecker,
    HealthStatus,
    ServiceHealth,
    HealthCheckResult,
)
from services_common.config import (
    AppSettings,
    DatabaseSettings,
    RedisSettings,
    LLMSettings,
    VectorStoreSettings,
    SecuritySettings,
    RateLimitSettings,
    MetricsSettings,
    Settings,
    get_settings,
)

__version__ = "2.0.0"

__all__ = [
    # Logging
    "Logger",
    "get_logger",
    # Response
    "ResponseCode",
    "ResponseResult",
    "DEFAULT_API_VERSION",
    "BaseResponse",
    "DataResponse",
    "ListResponse",
    "PageResponse",
    "ErrorResponse",
    "success",
    "created",
    "list_response",
    "page_response",
    "error",
    "bad_request",
    "unauthorized",
    "forbidden",
    "not_found",
    "conflict",
    # Exceptions
    "BaseException",
    "BaseDomainException",
    "BaseApplicationException",
    "NotFoundException",
    "AlreadyExistsException",
    "UnauthorizedException",
    "ForbiddenException",
    "ValidationException",
    "RateLimitException",
    "ServiceUnavailableException",
    "InvalidCredentialsException",
    "InvalidTokenException",
    "PasswordTooWeakException",
    "AuthenticationFailedException",
    "TokenExpiredException",
    "TokenBlacklistedException",
    # Exception_handler
    "register_base_exception_handlers",
    # Redis
    "RedisManager",
    # Database
    "BaseModel",
    "DatabaseManager",
    # Health Check
    "HealthChecker",
    "HealthStatus",
    "ServiceHealth",
    "HealthCheckResult",
    # Config
    "AppSettings",
    "DatabaseSettings",
    "RedisSettings",
    "LLMSettings",
    "VectorStoreSettings",
    "SecuritySettings",
    "RateLimitSettings",
    "MetricsSettings",
    "Settings",
    "get_settings",
    # Uvicorn Json Log
    "configure_uvicorn_logging",
    # Version
    "__version__",
]

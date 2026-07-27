"""Services Common Library - 所有服务共享的工具库"""

from services_common.logging import Logger, get_logger
from services_common.biz_code import BizCategory, make_biz_code, parse_biz_code
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
from services_common.decorators import handle_exceptions
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
    WorkersSettings,
    LLMSettings,
    VectorStoreSettings,
    SecuritySettings,
    RateLimitSettings,
    MetricsSettings,
    Settings,
    get_settings,
)
from services_common.shared_resources import SharedResources
from services_common.resource_keys import DB_DEFAULT_KEY, REDIS_DEFAULT_KEY, db_key, redis_key
from services_common.utils.id import generate_id

__version__ = "2.0.0"

__all__ = [
    # Logging
    "Logger",
    "get_logger",
    # BizCode
    "BizCategory",
    "make_biz_code",
    "parse_biz_code",
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
    # Decorators
    "handle_exceptions",
    # Redis
    "RedisManager",
    # Database
    "BaseModel",
    "DatabaseManager",
    "SharedResources",
    "DB_DEFAULT_KEY",
    "REDIS_DEFAULT_KEY",
    "db_key",
    "redis_key",
    # Health Check
    "HealthChecker",
    "HealthStatus",
    "ServiceHealth",
    "HealthCheckResult",
    # Config
    "AppSettings",
    "DatabaseSettings",
    "RedisSettings",
    "WorkersSettings",
    "LLMSettings",
    "VectorStoreSettings",
    "SecuritySettings",
    "RateLimitSettings",
    "MetricsSettings",
    "Settings",
    "get_settings",
    # Utils
    "generate_id",
    # Uvicorn Json Log
    "configure_uvicorn_logging",
    # Version
    "__version__",
]

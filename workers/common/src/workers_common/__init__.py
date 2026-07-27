"""Workers Common Library - 所有 worker 共享的工具库

与 services_common 的边界：
  - workers 不得依赖 services_common（领域边界隔离）
  - 本库仅包含 worker 运行所需能力：配置、数据库、Redis、日志、异常、
    共享资源、资源键、工具函数
  - 不包含任何 Web 专用能力（FastAPI/uvicorn、HTTP response、中间件、异常处理器）
"""

from workers_common.logging import (
    Logger,
    get_logger,
    configure_logging,
    reinit_file_logging,
    shutdown_file_logging,
)
from workers_common.exceptions import (
    BaseException,
    BaseDomainException,
    BaseApplicationException,
    NotFoundException,
    AlreadyExistsException,
    ValidationException,
    ServiceUnavailableException,
    InvalidCredentialsException,
    InvalidTokenException,
    PasswordTooWeakException,
)
from workers_common.database import BaseModel, DatabaseManager
from workers_common.redis import RedisManager, RedisWorkerLock
from workers_common.config import (
    AppSettings,
    DatabaseSettings,
    RedisSettings,
    LLMSettings,
    WorkersSettings,
    Settings,
    get_settings,
)
from workers_common.shared_resources import SharedResources
from workers_common.resource_keys import (
    DB_DEFAULT_KEY,
    REDIS_DEFAULT_KEY,
    db_key,
    redis_key,
    resource_key,
)
from workers_common.loghelper import mask_sensitive
from workers_common.utils.id import generate_id

__version__ = "2.0.0"

__all__ = [
    # Logging
    "Logger",
    "get_logger",
    "configure_logging",
    "reinit_file_logging",
    "shutdown_file_logging",
    # Exceptions
    "BaseException",
    "BaseDomainException",
    "BaseApplicationException",
    "NotFoundException",
    "AlreadyExistsException",
    "ValidationException",
    "ServiceUnavailableException",
    "InvalidCredentialsException",
    "InvalidTokenException",
    "PasswordTooWeakException",
    # Database
    "BaseModel",
    "DatabaseManager",
    # Redis
    "RedisManager",
    "RedisWorkerLock",
    # Config
    "AppSettings",
    "DatabaseSettings",
    "RedisSettings",
    "LLMSettings",
    "WorkersSettings",
    "Settings",
    "get_settings",
    # Shared resources
    "SharedResources",
    "DB_DEFAULT_KEY",
    "REDIS_DEFAULT_KEY",
    "db_key",
    "redis_key",
    "resource_key",
    # Log helper
    "mask_sensitive",
    # Utils
    "generate_id",
    # Version
    "__version__",
]
"""中间件模块 - 所有服务共享的中间件组件"""

# get_request_id 从根级 _context 导入，避免触发 middleware/__init__ 的循环
from services_common._context import get_request_id
from services_common.middleware.logger import LoggingMiddleware
from services_common.middleware.request_id import RequestIDMiddleware
from services_common.middleware.error_handling import (
    ErrorHandlingMiddleware,
    register_exception_handler,
)

__all__ = [
    "LoggingMiddleware",
    "RequestIDMiddleware",
    "get_request_id",
    "ErrorHandlingMiddleware",
    "register_exception_handler",
]

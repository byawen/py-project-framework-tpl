import time
import logging
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
logger = logging.getLogger(__name__)

class LoggingMiddleware(BaseHTTPMiddleware):
    """客户端/响应日志记录中间件"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.perf_counter()

        logger.info(
            f"请求开始: {request.method} {request.url.path}",
            extra={
                "method": request.method,
                "path": request.url.path,
                "client_host": request.client.host if request.client else None,
            }
        )

        response = await call_next(request)

        process_time = time.perf_counter() - start_time

        logger.info(
            f"请求完成: {request.method} {request.url.path} - {response.status_code} ({process_time:.3f}s)",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "process_time": process_time,
            }
        )

        response.headers["X-Process-Time"] = str(process_time)

        return response


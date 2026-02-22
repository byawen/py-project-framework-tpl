import logging
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
logger = logging.getLogger(__name__)

class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """全局错误处理中间件"""
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            logger.error(
                f"未处理的异常: {exc}",
                exc_info=True,
                extra={
                    "method": request.method,
                    "path": request.url.path,
                }
            )
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=500,
                content={
                    "message": "Internal server error",
                    "code": "INTERNAL_ERROR",
                    "details": {},
                }
            )

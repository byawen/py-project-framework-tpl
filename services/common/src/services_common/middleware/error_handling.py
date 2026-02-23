import logging
import os
from typing import Callable
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from services_common.response import ErrorResponse, ResponseCode

logger = logging.getLogger(__name__)


def _is_dev_environment(request: Request) -> bool:
    """判断是否为开发环境"""
    try:
        settings = request.app.state.settings
        return settings.DEBUG
    except Exception:
        return os.getenv("ENVIRONMENT", "development") == "development"


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """全局错误处理中间件"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            return await call_next(request)
        except BaseExceptionGroup as exc:
            # 处理异常组（Starlette 会将异常包装在 ExceptionGroup 中）
            # 只处理包含单一异常的情况
            if exc.subgroup and len(exc.subgroup) == 1:
                real_exc = exc.subgroup[0]
            else:
                real_exc = exc
            return self._handle_exception(request, real_exc)
        except Exception as exc:
            return self._handle_exception(request, exc)

    def _handle_exception(self, request: Request, exc: Exception) -> Response:
        """处理异常并返回 JSON 响应"""
        is_dev = _is_dev_environment(request)
        
        logger.error(
            f"未处理的异常: {exc}",
            exc_info=True,
            extra={
                "method": request.method,
                "path": request.url.path,
            }
        )

        if is_dev:
            # 开发环境：返回详细信息
            response = ErrorResponse(
                code=ResponseCode.INTERNAL_SERVER_ERROR,
                message="Internal server error",
                detail=str(exc),
            )
        else:
            # 生产环境：只返回通用信息
            response = ErrorResponse(
                code=ResponseCode.INTERNAL_SERVER_ERROR,
                message="Internal server error",
                detail=None,
            )

        return JSONResponse(
            status_code=ResponseCode.INTERNAL_SERVER_ERROR,
            content=response.model_dump(mode="json"),
        )

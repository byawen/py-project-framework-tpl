"""全局错误处理中间件 - 捕获未处理异常并返回统一 JSON 响应

纯 ASGI 实现，不依赖 BaseHTTPMiddleware，消除 cancel scope 对 SQLAlchemy
异步连接池的影响，同时正确支持 SSE / StreamingResponse。

各服务可通过 ``register_exception_handler`` 注册领域异常处理回调，
中间件会按注册顺序依次尝试，首个返回 JSONResponse 的回调胜出。
未匹配的异常仍走默认 500 逻辑。
"""

from __future__ import annotations

from typing import Any, Callable

from fastapi.responses import JSONResponse

from services_common._context import get_request_id
from services_common.logging import get_logger
from services_common.response import ErrorResponse, ResponseCode

logger = get_logger(__name__)

# 异常类型 → 处理回调（模块级注册表，各服务启动时注册）
_exception_handlers: dict[type[Exception], Callable[[Exception], JSONResponse]] = {}


def register_exception_handler(
    exc_type: type[Exception],
    handler: Callable[[Exception], JSONResponse],
) -> None:
    """注册领域异常处理回调。

    handler 接收异常实例，返回 JSONResponse；若返回 None 则跳过，继续匹配下一个。
    """
    _exception_handlers[exc_type] = handler


class ErrorHandlingMiddleware:
    """全局错误处理中间件（纯 ASGI 实现）"""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(
        self, scope: dict[str, Any], receive: Callable, send: Callable
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers_sent = False

        async def send_wrapper(message: dict[str, Any]) -> None:
            nonlocal headers_sent
            if message["type"] == "http.response.start":
                headers_sent = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except BaseExceptionGroup as exc:
            if exc.subgroup and len(exc.subgroup) == 1:
                real_exc = exc.subgroup[0]
            else:
                real_exc = exc
            await self._handle_error(scope, receive, send, headers_sent, real_exc)
        except Exception as exc:
            await self._handle_error(scope, receive, send, headers_sent, exc)

    async def _handle_error(
        self,
        scope: dict[str, Any],
        receive: Callable,
        send: Callable,
        headers_sent: bool,
        exc: BaseException,
    ) -> None:
        request_id = get_request_id()
        method = scope.get("method", "")
        path = scope.get("path", "")

        if headers_sent:
            # 响应头已发出，无法再发送错误响应，只能记录日志
            logger.error(
                f">>>> ERROR LOG: {exc}",
                operation="http.request.error.handler",
                method=method,
                path=path,
                request_id=request_id,
                exc_info=True,
            )
            return

        # 先尝试已注册的领域异常处理器（业务校验异常等，不应打 ERROR 级别日志）
        domain_response = self._try_domain_handlers(exc, request_id)
        if domain_response is not None:
            await domain_response(scope, receive, send)
            return

        # 未匹配领域 handler 的异常才是真正的程序异常，打 ERROR 日志
        logger.error(
            f">>>> ERROR LOG: {exc}",
            operation="http.request.error.handler",
            method=method,
            path=path,
            request_id=request_id,
            exc_info=True,
        )

        response = ErrorResponse(
            code=ResponseCode.INTERNAL_SERVER_ERROR,
            message="Internal server error",
            detail=None,
            trace_id=request_id,
        )

        error_response = JSONResponse(
            status_code=ResponseCode.INTERNAL_SERVER_ERROR,
            content=response.model_dump(mode="json"),
        )
        await error_response(scope, receive, send)

    @staticmethod
    def _try_domain_handlers(
        exc: BaseException, request_id: str
    ) -> JSONResponse | None:
        """按注册类型匹配领域异常 handler，返回 JSONResponse 或 None。"""
        for exc_type, handler in _exception_handlers.items():
            if isinstance(exc, exc_type):
                resp = handler(exc)
                if resp is not None:
                    return resp
        return None
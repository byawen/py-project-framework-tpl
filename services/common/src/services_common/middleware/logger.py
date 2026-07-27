"""日志记录中间件 - 记录每个 HTTP 请求的耗时和状态码

纯 ASGI 实现，不依赖 BaseHTTPMiddleware，消除 cancel scope 对 SQLAlchemy
异步连接池的影响，同时正确支持 SSE / StreamingResponse。
"""

from __future__ import annotations

import time
from typing import Any, Callable

from services_common._context import get_request_id
from services_common.logging import get_logger

logger = get_logger(__name__)


class LoggingMiddleware:
    """记录请求开始/结束、耗时、状态码（纯 ASGI 实现）"""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(
        self, scope: dict[str, Any], receive: Callable, send: Callable
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = get_request_id()
        start_time = time.perf_counter()
        method = scope.get("method", "")
        path = scope.get("path", "")
        query = scope.get("query_string", b"").decode()
        client = scope.get("client")
        raw_headers = dict(scope.get("headers", []))
        user_agent = raw_headers.get(b"user-agent", b"").decode()

        logger.info(
            f"-->>>> REQUEST START: {method} {path}",
            operation="http.request.start",
            request_id=request_id,
            method=method,
            path=path,
            query_params=query,
            client_host=client[0] if client else None,
            user_agent=user_agent or None,
        )

        # 拦截 send：采集 status_code + 注入 X-Process-Time
        status_code: int | None = None

        async def send_wrapper(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                process_time = time.perf_counter() - start_time
                hdrs = list(message.get("headers", []))
                hdrs.append((b"x-process-time", f"{process_time}".encode()))
                message["headers"] = hdrs
            await send(message)

        await self.app(scope, receive, send_wrapper)

        process_time = time.perf_counter() - start_time
        logger.info(
            f"<<<<-- REQUEST END: {method} {path}",
            operation="http.request.finish",
            request_id=request_id,
            method=method,
            path=path,
            status_code=status_code,
            process_time=round(process_time, 3),
        )
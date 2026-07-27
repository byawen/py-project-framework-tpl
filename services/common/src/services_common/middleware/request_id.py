"""RequestID 中间件 - 为每个请求注入 request_id 并记录请求/响应日志

纯 ASGI 实现，不依赖 BaseHTTPMiddleware，消除 cancel scope 对 SQLAlchemy
异步连接池的影响，同时正确支持 SSE / StreamingResponse。
"""

from __future__ import annotations

import time
from typing import Any, Callable

from services_common._context import request_id_context
from services_common.logging import get_logger
from services_common.utils.id import generate_id

logger = get_logger(__name__)


class RequestIDMiddleware:
    """为每个请求添加 request_id 并记录请求/响应日志（纯 ASGI 实现）"""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(
        self, scope: dict[str, Any], receive: Callable, send: Callable
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 从请求头提取或生成 request_id
        headers: dict[bytes, bytes] = dict(scope.get("headers", []))
        request_id = headers.get(b"x-request-id", b"").decode() or generate_id()

        # 设置 ContextVar
        token = request_id_context.set(request_id)

        # 写入 scope["state"] 以便下游 request.state.request_id 可用
        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["request_id"] = request_id

        # 读取请求体用于日志（仅 JSON，与原实现一致）
        content_type = headers.get(b"content-type", b"").decode().lower()
        log_body: bytes | None = None
        downstream_receive = receive

        if "application/json" in content_type:
            log_body, downstream_receive = await self._tee_body(receive)

        start_time = time.time()
        method = scope.get("method", "")
        path = scope.get("path", "")
        client = scope.get("client")
        client_host = client[0] if client else "unknown"

        logger.info(
            f"---> {method} {path}",
            operation="http.request.request-id",
            request_id=request_id,
            client=client_host,
            body=log_body,
        )

        # 拦截 send：注入 X-Request-ID 响应头 + 采集非流式响应体用于日志
        status_code: int | None = None
        saw_more_body = False
        res_body: bytes | None = None

        async def send_wrapper(message: dict[str, Any]) -> None:
            nonlocal status_code, saw_more_body, res_body

            if message["type"] == "http.response.start":
                status_code = message["status"]
                hdrs = list(message.get("headers", []))
                hdrs.append((b"x-request-id", request_id.encode()))
                message["headers"] = hdrs

            elif message["type"] == "http.response.body":
                if message.get("more_body", False):
                    saw_more_body = True
                elif not saw_more_body:
                    body = message.get("body", b"")
                    if body and len(body) <= 4096:
                        res_body = body
            await send(message)

        try:
            await self.app(scope, downstream_receive, send_wrapper)
        except Exception:
            process_time = time.time() - start_time
            logger.error(
                f"<--- {method} {path}",
                operation="http.request.request-id.start",
                request_id=request_id,
                status=500,
                duration=round(process_time, 3),
                error="exception",
            )
            raise
        finally:
            request_id_context.reset(token)

        # 响应体日志（仅非流式响应）
        # res_body 赋值时已限制 <= 4096，无需二次截断
        process_time = time.time() - start_time
        logger.info(
            f"<--- {method} {path}",
            operation="http.request.request-id.finish",
            request_id=request_id,
            status=status_code,
            duration=round(process_time, 3),
            body=res_body,
        )

    @staticmethod
    async def _tee_body(receive: Callable) -> tuple[bytes | None, Callable]:
        """消费 receive 读取完整请求体，返回 (日志体, 可回放的 receive)。

        日志体超过 4KB 时截断为首 1KB + 尾 1KB，与原实现一致。
        回放 receive 在缓冲消息耗尽后回退到原始 receive（用于 http.disconnect）。
        """
        chunks: list[bytes] = []
        messages: list[dict[str, Any]] = []
        more = True

        while more:
            msg = await receive()
            if msg["type"] == "http.disconnect":
                messages.append(msg)
                break
            messages.append(msg)
            chunk = msg.get("body", b"")
            if chunk:
                chunks.append(chunk)
            more = msg.get("more_body", False)

        full = b"".join(chunks)
        log_body: bytes | None = None
        if full:
            log_body = (
                full[:1024] + b" ... " + full[-1024:]
                if len(full) > 4096
                else full
            )

        it = iter(messages)

        async def replay() -> dict[str, Any]:
            try:
                return next(it)
            except StopIteration:
                return await receive()

        return log_body, replay
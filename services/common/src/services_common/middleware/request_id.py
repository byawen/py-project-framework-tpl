import uuid
import logging
import time
from contextvars import ContextVar
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# 用于在线程/异步任务中传递 request_id
request_id_context: ContextVar[str] = ContextVar("request_id", default="")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """为每个请求添加请求ID并记录请求/响应的中间件"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())

        # 设置到 contextvars，供整个链路使用
        token = request_id_context.set(request_id)
        request.state.request_id = request_id

        # 记录传入的请求
        start_time = time.time()
        logger.info(
            f"--> {request.method} {request.url.path} "
            f"[request_id={request_id}] "
            f"client={request.client.host if request.client else 'unknown'}"
        )

        response = None
        try:
            response = await call_next(request)
        except Exception:
            # 异常时记录错误日志
            process_time = time.time() - start_time
            logger.error(
                f"<-- {request.method} {request.url.path} "
                f"[request_id={request_id}] "
                f"status=500 "
                f"duration={process_time:.3f}s "
                f"error=exception"
            )
            raise
        finally:
            # 清理 contextvars
            request_id_context.reset(token)

        # 记录传出的响应
        process_time = time.time() - start_time
        logger.info(
            f"<-- {request.method} {request.url.path} "
            f"[request_id={request_id}] "
            f"status={response.status_code} "
            f"duration={process_time:.3f}s"
        )

        response.headers["X-Request-ID"] = request_id

        return response


def get_request_id() -> str:
    """获取当前请求的 request_id
    
    用于在业务代码中获取当前请求的 request_id
    
    Returns:
        request_id 字符串，如果不在请求上下文中则返回空字符串
    """
    return request_id_context.get()

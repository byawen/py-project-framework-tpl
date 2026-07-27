"""Endpoint 异常捕获装饰器

为接口层提供防御性异常捕获，将未处理的底层异常（SQL、Redis 等）
转换为安全的 HTTPException，防止内部细节泄露到前端。
"""
import functools
from typing import Any, Callable

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError

from services_common.exceptions import BaseDomainException, BaseApplicationException
from services_common.exception_handlers import _get_logger


def handle_exceptions(func: Callable) -> Callable:
    """Endpoint 异常捕获装饰器

    用法::

        @router.get("/items/{item_id}")
        @handle_exceptions
        async def get_item(item_id: str):
            ...

    行为：
    - BaseDomainException / BaseApplicationException：直接透出，由全局 handler 处理
    - HTTPException / RequestValidationError：直接透出，由全局 handler 处理
    - 其他 Exception（SQLAlchemy、Redis、网络等）：记录日志后转为 HTTPException(500)，
      由全局 http_exception_handler 脱敏返回
    """
    @functools.wraps(func)
    async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await func(*args, **kwargs)
        except (BaseDomainException, BaseApplicationException,
                HTTPException, RequestValidationError):
            raise
        except Exception as exc:
            logger = _get_logger()
            logger.error(
                f"Endpoint {func.__name__} unhandled exception: {exc}",
                operation=f"endpoint.{func.__name__}",
                exc_info=True,
            )
            raise HTTPException(status_code=500) from exc

    @functools.wraps(func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except (BaseDomainException, BaseApplicationException,
                HTTPException, RequestValidationError):
            raise
        except Exception as exc:
            logger = _get_logger()
            logger.error(
                f"Endpoint {func.__name__} unhandled exception: {exc}",
                operation=f"endpoint.{func.__name__}",
                exc_info=True,
            )
            raise HTTPException(status_code=500) from exc

    import asyncio
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper
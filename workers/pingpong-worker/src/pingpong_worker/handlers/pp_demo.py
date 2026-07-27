"""PingPong 任务处理器

示例 handler，处理 pingpong 类型的消息任务。
"""

import asyncio
import json
from typing import Any

from pingpong_worker.foundation.container import get_injector
from pingpong_worker.foundation.logging import get_logger

logger = get_logger(__name__)


def handle_pingpong_task(
    self, payload: dict[str, Any] | None = None, **kwargs: Any
) -> dict[str, Any]:
    """处理 PingPong 任务

    Celery task handler，同步入口，内部调度异步逻辑。
    兼容 kwargs 风格（services_common.task_publisher 统一协议）和旧 args 风格。

    Args:
        self: Celery task instance (bind=True)
        payload: 任务载荷（旧 args 风格，可选）
        **kwargs: 任务载荷字段（kwargs 风格，推荐）

    Returns:
        处理结果
    """
    raw = dict(payload) if payload else dict(kwargs)
    logger.info(f"Received pingpong task", payload=raw)

    try:
        # 在同步 Celery worker 中运行异步代码
        result = asyncio.run(_async_handle_pingpong(raw))
        logger.info(f"Pingpong task completed", result=result)
        return result
    except Exception as e:
        logger.error(f"Pingpong task failed", error=str(e), payload=raw)
        raise


async def _async_handle_pingpong(payload: dict[str, Any]) -> dict[str, Any]:
    """异步处理逻辑 — 调用 Application 层"""
    injector = get_injector()

    from pingpong_worker.app.application.services.pp_service import PPService

    pp_service = injector.get(PPService)

    message = payload.get("message", "ping")
    data = payload.get("data", "pong")

    ping, pong = await pp_service.ping_and_pong(message, data)

    return {
        "ping_id": ping.ping_id,
        "pong_id": pong.pong_id,
        "message": ping.message,
        "data": pong.data,
    }

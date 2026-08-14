"""Echo 任务处理器（入口适配层，等价 service 的 endpoint）

只做四件事：解析 payload → 调度异步 → 调用 application → 组装结果。
不含业务逻辑。

Celery 同步入口内用 workers_common.async_bridge.run_async 在当前工作线程的
thread-local 持久 loop 上调度异步（Option B）。禁止 asyncio.run()（每任务新建/关
loop，破坏 asyncpg 连接池绑定的 loop）。
"""

from typing import Any

from workers_common.async_bridge import run_async

from pingpong_worker.foundation.container import get_injector
from pingpong_worker.foundation.logging import get_logger
from pingpong_worker.handlers.schemas import EchoTaskPayload, EchoTaskResult

logger = get_logger(__name__)


def handle_echo_task(
    self, payload: dict[str, Any] | None = None, **kwargs: Any
) -> dict[str, Any]:
    """处理 echo 任务

    Celery task handler，同步入口，内部调度异步逻辑。
    兼容 kwargs 风格（services_common.task_publisher 统一协议）和旧 args 风格。

    Args:
        self: Celery task instance (bind=True)
        payload: 任务载荷（旧 args 风格，可选）
        **kwargs: 任务载荷字段（kwargs 风格，推荐）

    Returns:
        处理结果（含 pong_id 与 message）
    """
    raw = dict(payload) if payload else dict(kwargs)
    logger.info("收到 echo 任务", operation="pingpong.echo_task.received", payload=raw)
    try:
        result = run_async(_async_handle_echo(raw))
        logger.info("echo 任务完成", operation="pingpong.echo_task.success", result=result)
        return result
    except Exception as e:
        logger.error("echo 任务失败", operation="pingpong.echo_task.error", error=str(e), payload=raw)
        raise


async def _async_handle_echo(raw: dict[str, Any]) -> dict[str, Any]:
    """异步处理逻辑 — 队列裸 dict → Pydantic 模型 → application"""
    data = EchoTaskPayload(**raw)  # 队列边界处转模型，禁止把裸 dict 传进 application

    injector = get_injector()
    from pingpong_worker.app.application.services.pp_service import PPService

    pp_service = injector.get(PPService)
    pong = await pp_service.create_pong(data.message)

    # 返回值序列化进 result backend，用模型 .model_dump() 而非手拼 dict
    return EchoTaskResult(
        pong_id=pong.pong_id,
        message=data.message,
    ).model_dump()

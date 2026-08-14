"""Beat 定时任务模板 handler

由 Celery Beat 定时调度（见 config PIPO_CELERY_BEAT_SCHEDULE），
作为新 worker 的 Beat 定时任务参考实现。

多节点幂等保护：
- Redis 分布式锁确保同一时刻只有一个节点执行
- 锁 TTL 覆盖单次执行最大耗时，防止死锁

───────────────────────────────────────
新增 Beat handler 流程：
1. 复制本文件，改名为 <your_beat>_handler.py
2. 修改 _LOCK_KEY / _LOCK_TTL / topic 和实际业务逻辑
3. 在 config.py PIPO_CELERY_BEAT_SCHEDULE 中添加调度条目
4. 在 config.py PIPO_CELERY_TASK_ROUTES 中添加路由
5. 在 registry.py 中 import 并 register_handler
───────────────────────────────────────
"""

import uuid
from typing import Any

from pingpong_worker.foundation.container import get_injector
from pingpong_worker.foundation.logging import get_logger
from workers_common.async_bridge import run_async as _run_async

logger = get_logger(__name__)

_LOCK_KEY = "pipo:beat_demo:leader"
_LOCK_TTL = 120  # 2 分钟，覆盖单次执行最大耗时


def handle_beat_demo(self, **kwargs: Any) -> dict[str, Any]:
    """Celery Beat 定时任务：模板示例，定时输出心跳日志。

    替换为实际业务逻辑时：
    - 移除 _async_dummy_heartbeat，换为真实异步业务调用
    - 通过 get_injector() 获取 Application Service 执行业务
    """
    acquired, lock_owner = _run_async(_try_acquire_lock())
    if not acquired:
        logger.debug(
            "Beat demo skipped: another node holds the lock (owner=%s)",
            lock_owner,
        )
        return {"skipped": True, "lock_owner": lock_owner}

    logger.info(
        "Beat demo: lock acquired (owner=%s)",
        lock_owner,
        operation="pingpong_worker.beat_demo.lock_acquired",
    )
    try:
        result = _run_async(_async_execute(lock_owner))
        logger.info(
            "Beat demo completed",
            operation="pingpong_worker.beat_demo.done",
            **result,
        )
        return result
    except Exception as exc:
        logger.error(
            "Beat demo failed: %s",
            exc,
            operation="pingpong_worker.beat_demo.error",
        )
        return {"skipped": False, "lock_owner": lock_owner, "error": str(exc)}


async def _try_acquire_lock() -> tuple[bool, str]:
    """尝试获取 Redis 分布式锁。"""
    from workers_common.redis import RedisManager

    injector = get_injector()
    rm = injector.get(RedisManager)

    lock_owner = str(uuid.uuid4())[:8]
    acquired = await rm.set(
        _LOCK_KEY,
        lock_owner,
        nx=True,
        ex=_LOCK_TTL,
    )
    if acquired:
        return True, lock_owner

    current_owner = await rm.get(_LOCK_KEY)
    return False, current_owner or "unknown"


async def _async_execute(lock_owner: str) -> dict[str, Any]:
    """实际业务逻辑 — 模板中仅输出心跳，替换为真实 Service 调用。

    示例：
        injector = get_injector()
        service = injector.get(YourService)
        return await service.do_scheduled_work()
    """
    logger.info(
        "Beat demo executing",
        lock_owner=lock_owner,
        operation="pingpong_worker.beat_demo.executing",
    )
    return {
        "skipped": False,
        "lock_owner": lock_owner,
        "message": "beat demo heartbeat",
    }
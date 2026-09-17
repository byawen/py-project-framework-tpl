"""Beat 定时任务模板 handler

由 Celery Beat 定时调度（见 config PIPO_CELERY_BEAT_SCHEDULE），
作为新 worker 的 Beat 定时任务参考实现。

多节点幂等保护：
- RedisWorkerLock 分布式锁确保同一时刻只有一个节点执行（带自动续期）
- 锁 TTL 覆盖单次执行最大耗时，防止死锁

> acquire+业务+release 收进同一个 async 函数（一次 _run_async），续期 task 才能存活。

───────────────────────────────────────
新增 Beat handler 流程：
1. 复制本文件，改名为 <your_beat>_handler.py
2. 修改 _LOCK_KEY / _LOCK_TTL / topic 和实际业务逻辑
3. 在 config.py PIPO_CELERY_BEAT_SCHEDULE 中添加调度条目
4. 在 config.py PIPO_CELERY_TASK_ROUTES 中添加路由
5. 在 registry.py 中 import 并 register_handler
───────────────────────────────────────
"""

import socket
import uuid
from typing import Any

from pingpong_worker.foundation.container import get_injector
from pingpong_worker.foundation.logging import get_logger
from workers_common.async_bridge import run_async as _run_async

logger = get_logger(__name__)

_INSTANCE_ID = f"{socket.gethostname()}:{uuid.uuid4().hex}"
_LOCK_KEY = "pipo:beat_demo:leader"
_LOCK_TTL = 120  # 2 分钟，覆盖单次执行最大耗时


def handle_beat_demo(self, **kwargs: Any) -> dict[str, Any]:
    """Celery Beat 定时任务：模板示例，定时输出心跳日志。

    替换为实际业务逻辑时：
    - 移除 _async_dummy_heartbeat，换为真实异步业务调用
    - 通过 get_injector() 获取 Application Service 执行业务
    """
    return _run_async(_async_beat_demo())


async def _async_beat_demo() -> dict[str, Any]:
    from workers_common.redis import RedisManager, RedisWorkerLock

    injector = get_injector()
    redis_manager = injector.get(RedisManager)
    lock = RedisWorkerLock(
        redis=redis_manager,
        lock_key=_LOCK_KEY,
        ttl_seconds=_LOCK_TTL,
        renew_seconds=max(60, _LOCK_TTL // 3),
        owner_id=_INSTANCE_ID,
    )
    if not await lock.acquire():
        current_owner = await redis_manager.get(_LOCK_KEY)
        lock_owner = current_owner or "unknown"
        logger.debug(
            "Beat demo skipped: another node holds the lock (owner=%s)",
            lock_owner,
        )
        return {"skipped": True, "lock_owner": lock_owner}

    logger.info(
        "Beat demo: lock acquired (owner=%s)",
        _INSTANCE_ID,
        operation="pingpong_worker.beat_demo.lock_acquired",
    )
    lock.start_auto_renew()
    try:
        result = await _async_execute(_INSTANCE_ID)
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
        return {"skipped": False, "lock_owner": _INSTANCE_ID, "error": str(exc)}
    finally:
        try:
            await lock.stop_auto_renew()
            await lock.release()
        except Exception:
            logger.warning("Failed to release beat demo lock", exc_info=True)


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
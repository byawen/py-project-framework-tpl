"""持久 event loop — 所有 Celery 同步 handler 共用。

Celery 任务在同步线程中执行，不能每次 asyncio.run() 创建新 loop，
否则 DatabaseManager 的 asyncpg 连接池会绑定到已关闭的旧 loop。
用一个后台线程跑持久 loop，所有 async 调用通过 run_coroutine_threadsafe 提交。
"""

import asyncio
import threading

from pingpong_worker.foundation.logging import get_logger

logger = get_logger(__name__)

_persistent_loop: asyncio.AbstractEventLoop | None = None
_loop_thread: threading.Thread | None = None
_loop_lock = threading.Lock()


def get_persistent_loop() -> asyncio.AbstractEventLoop:
    """获取（必要时创建）持久 event loop，运行在专用后台线程。"""
    global _persistent_loop, _loop_thread
    with _loop_lock:
        if _persistent_loop is not None and not _persistent_loop.is_closed():
            return _persistent_loop
        _persistent_loop = asyncio.new_event_loop()
        _loop_thread = threading.Thread(
            target=_persistent_loop.run_forever,
            name="pingpong-async-loop",
            daemon=True,
        )
        _loop_thread.start()
        logger.info("Persistent event loop started in background thread")
        return _persistent_loop


def run_async(coro):
    """在持久 loop 上执行 coroutine 并同步等待结果。"""
    loop = get_persistent_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()
"""Sync → async bridge for Celery ``--pool=threads`` (Option B).

Each Celery worker thread owns a **thread-local persistent event loop**. A task
drives the loop directly on the owning worker thread via
``loop.run_until_complete(coro)``; the loop is created once and **reused across
tasks**. There is no background ``run_forever`` thread and no per-task
``asyncio.run``.

Why this model is correct
-------------------------
1. **No deadlock.** ``run_until_complete`` is driven by the same thread that
   owns the loop, so the coroutine actually executes (unlike
   ``run_coroutine_threadsafe`` + ``future.result()`` without a ``run_forever``
   driver, which hangs forever).
2. **No crash.** The historical "This event loop is already running" crash came
   from a *module-global* loop shared by multiple threads. With a thread-local
   loop, and Celery's threads pool running **one task per thread at a time**,
   there is never a concurrent ``run_until_complete`` on the same loop.
3. **Permissible repeated calls.** ``run_until_complete`` may be called
   repeatedly on a non-running loop by its owning thread; the loop is not
   closed, so asyncpg / redis.asyncio pools bind to it once and are reused
   across tasks — no "Event loop is closed", no connection storm.
4. **No extra threads.** The loop runs on the worker thread itself; no
   cross-thread future hopping (cheaper than a per-thread daemon loop).
5. **contextvars propagate naturally.** The coroutine runs on the owning thread;
   ``copy_context`` gives per-task isolation so an in-task write cannot leak to
   the next task on the same thread.
6. **prefork compatible.** In a prefork pool worker, a single thread drives the
   loop and Option B degrades to "one loop per process, one
   ``run_until_complete`` per task" — identical to the historical strategy-A
   behaviour, with no regression. The same ``run_async`` therefore works under
   both pools.

Invariant
---------
No ``asyncio.create_task`` may outlive its ``run_until_complete`` call. Any
background task must be awaited or cancelled before the top-level coroutine
returns. The current worker codebase satisfies this (``RedisWorkerLock``
auto-renew is never used inside workers — only by FastAPI services running on
their own uvicorn loop).
"""

from __future__ import annotations

import asyncio
import contextvars
import threading
from typing import Awaitable, TypeVar

T = TypeVar("T")

_loop_store = threading.local()


def get_thread_loop() -> asyncio.AbstractEventLoop:
    """Return this thread's persistent event loop, creating it lazily.

    The loop is bound to the current thread via ``threading.local`` and reused
    for every subsequent ``run_async`` on this thread. It is NOT closed between
    tasks, so connection pools that bind to it remain valid across tasks.
    """
    loop = getattr(_loop_store, "loop", None)
    if loop is not None and not loop.is_closed():
        return loop
    loop = asyncio.new_event_loop()
    _loop_store.loop = loop
    _loop_store.thread_id = threading.get_ident()
    return loop


def _is_in_loop_thread() -> bool:
    """True when called from within a running event loop.

    Guards against reentrant ``run_async`` calls (a coroutine that itself calls
    ``run_async``). Reentry would deadlock because the owning loop is already
    running ``run_until_complete``; raising is the safe, loud failure.
    """
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


def run_async(coro: Awaitable[T]) -> T:
    """Run *coro* to completion on this thread's persistent loop and return it.

    Must be called from a plain (non-async) thread — i.e. a Celery handler
    entry point, never from inside a coroutine.
    """
    if _is_in_loop_thread():
        raise RuntimeError(
            "run_async() must not be called from within a running event loop "
            "(reentrant call would deadlock)"
        )
    loop = get_thread_loop()
    ctx = contextvars.copy_context()
    return ctx.run(lambda: loop.run_until_complete(coro))


def dispose_thread_loop() -> None:
    """Best-effort teardown of the *current thread's* loop and resources.

    Called from a process-level ``worker_shutdown`` signal or ``atexit`` hook.
    Celery's threads pool does not emit a per-thread teardown signal, so worker
    threads' loops are reaped by the OS at process exit; this hook covers the
    main-thread / process-shutdown path and is safe to call unconditionally.
    """
    loop = getattr(_loop_store, "loop", None)
    if loop is None or loop.is_closed():
        _loop_store.loop = None
        return
    # Close thread-local DB/Redis managers (bound to this loop) before the loop
    # goes away, so pooled connections are released rather than orphaned.
    try:
        from workers_common import thread_resources as _tr

        loop.run_until_complete(_tr.dispose_thread_resources())
    except Exception:  # noqa: BLE001 — teardown must never raise
        pass
    try:
        loop.close()
    except Exception:  # noqa: BLE001
        pass
    _loop_store.loop = None


def reset_thread_local() -> None:
    """Drop the *current thread's* inherited thread-local loop + resource cache.

    Why: ``multiprocessing`` fork is copy-on-write. ``threading.local`` data is
    keyed by thread ident, and a forked child's **main thread** keeps the parent
    main thread's ident — so it inherits the parent's ``_loop_store.loop`` and
    ``_store.registry``. If the parent ever built a loop / manager before fork
    (e.g. via ``asyncio.run(setup)``), the child would reuse a loop bound to a
    now-closed parent loop, or a manager pool pinned to it →
    "Event loop is closed" / "Future attached to a different loop".

    When: call this from Celery's ``worker_process_init`` signal — it fires in
    every prefork pool worker (and prefork'd beat carrier) right after the
    second-layer fork, on the child's main thread, *before* any task runs.
    Under ``--pool=threads`` there is no second fork and the signal does not
    fire, so this is a harmless no-op there.

    The loop side is also guarded by ``get_thread_loop``'s ``is_closed()`` check,
    but the resource cache (``thread_resources``) is not — this reset is the
    single, explicit defense for both.
    """
    _loop_store.loop = None
    try:
        from workers_common import thread_resources as _tr

        _tr._reset_registry()
    except Exception:  # noqa: BLE001 — teardown path, never raise
        pass


def install_shutdown_hook() -> None:
    """Wire ``dispose_thread_loop`` into Celery's worker_shutdown signal + atexit.

    Idempotent. Safe to call from every worker's ``setup()``; the signal is
    process-level so only the registration that runs last sticks (they all point
    to the same function).

    Also wires ``reset_thread_local`` into ``worker_process_init`` so that every
    prefork pool worker (second-layer fork) drops any parent-main-thread
    thread-local it inherited — defending the fork path described in
    :func:`reset_thread_local`. Under ``--pool=threads`` the signal does not
    fire and only the atexit/shutdown hooks matter.
    """
    import atexit

    atexit.register(dispose_thread_loop)
    try:
        from celery.signals import worker_shutdown, worker_process_init

        worker_shutdown.connect(
            lambda **_: dispose_thread_loop(), weak=False, name="async_bridge.dispose"
        )
        worker_process_init.connect(
            lambda **_: reset_thread_local(), weak=False, name="async_bridge.reset"
        )
    except Exception:  # noqa: BLE001 — celery not always present (e.g. tests)
        pass

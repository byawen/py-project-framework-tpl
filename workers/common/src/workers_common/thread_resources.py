"""Thread-local resource accessors for Celery ``--pool=threads``.

Each worker thread gets its own ``DatabaseManager`` / ``RedisManager``, bound to
that thread's persistent event loop (see :mod:`workers_common.async_bridge`).
This solves the injector *singleton trap*: when a manager is bound as a
singleton it is created once (on the first thread that triggers it) and its
connection pool is pinned to that thread's loop; every other thread reusing it
crashes with "Future attached to a different loop" / "Event loop is closed".

Because Celery's threads pool runs one task per thread at a time, a per-thread
manager is also safe under ``--pool=prefork`` (where it degrades to one manager
per process — the single worker thread owns it). The same accessor therefore
works under both pools with no branching.

Workers wire these accessors into their injector so that
``injector.get(DatabaseManager)`` / ``injector.get(RedisManager)`` return the
*current thread's* manager. The accessor is cached per thread: the factory runs
at most once per (thread, key).
"""

from __future__ import annotations

import inspect
import threading
from typing import Any, Callable, TypeVar

T = TypeVar("T")

_store = threading.local()

# Sentinel distinct from None (a factory might legitimately return None, though
# our managers never do). Keeping an explicit sentinel avoids re-running the
# factory on every miss.
_MISSING = object()


def _registry() -> dict[str, Any]:
    reg = getattr(_store, "registry", None)
    if reg is None:
        reg = {}
        _store.registry = reg
    return reg


def get_or_create(key: str, factory: Callable[[], T]) -> T:
    """Return the current thread's instance for *key*, creating it via *factory*.

    The factory runs at most once per (thread, key); subsequent calls return the
    cached instance. The instance is expected to lazily bind its connection pool
    to the current thread's loop on first use (``DatabaseManager`` /
    ``RedisManager`` both do this via lazy ``@property`` accessors).
    """
    reg = _registry()
    obj = reg.get(key, _MISSING)
    if obj is _MISSING:
        obj = factory()
        reg[key] = obj
    return obj  # type: ignore[return-value]


def get(key: str, default: Any = None) -> Any:
    """Return the current thread's instance for *key*, or *default* if absent."""
    reg = getattr(_store, "registry", None)
    if reg is None:
        return default
    obj = reg.get(key, _MISSING)
    return default if obj is _MISSING else obj


def _reset_registry() -> None:
    """Drop the current thread's resource cache (does NOT close anything).

    Used by :func:`workers_common.async_bridge.reset_thread_local` from the
    ``worker_process_init`` signal so a freshly forked prefork pool worker does
    not reuse a parent-main-thread manager whose pool is bound to a dead loop.
    The loop is reset separately in ``async_bridge``; here we only clear the
    cache so the next ``get_or_create`` rebuilds on the child's own loop.
    """
    _store.registry = {}


class DBDisabledError(RuntimeError):
    """该 worker 的 DB 池已被 DB_ENABLED=False 关闭。仅 DB-FREE worker 可关。

    DB-HEAVY worker 误关会在首次 ``injector.get(DatabaseManager)`` 时抛此错 fail-fast，
    避免静默 None 潜伏成 NPE。
    """


class RedisDisabledError(RuntimeError):
    """该 worker 的 Redis 池已被 REDIS_ENABLED=False 关闭。仅 Redis-FREE worker 可关。"""


def get_or_create_db_manager(settings: Any):
    """Return this thread's ``DatabaseManager`` (small pool, overflow released).

    Bound to this thread's loop via :func:`workers_common.async_bridge.get_thread_loop`.
    DB_ENABLED=False 时 fail-fast 抛 DBDisabledError，不建池（仅 DB-FREE worker 可关）。
    """
    if not getattr(settings, "DB_ENABLED", True):
        raise DBDisabledError(
            f"DB disabled for worker (DB_ENABLED=False). "
            f"Only DB-FREE workers may set this. Worker: {getattr(settings, 'APP_NAME', '?')}"
        )
    from workers_common.database import DatabaseManager

    return get_or_create(
        "db:default",
        lambda: DatabaseManager(
            database_url=settings.DATABASE_URL,
            pool_size=getattr(settings, "DB_POOL_SIZE_PER_THREAD", 5),
            max_overflow=getattr(settings, "DB_MAX_OVERFLOW_PER_THREAD", 10),
            echo=settings.DB_ECHO,
            statement_timeout_ms=getattr(settings, "DB_STATEMENT_TIMEOUT_MS", 300000),
        ),
    )


def get_or_create_redis_manager(settings: Any):
    """Return this thread's ``RedisManager`` (small pool).

    REDIS_ENABLED=False 时 fail-fast 抛 RedisDisabledError，不建池。
    """
    if not getattr(settings, "REDIS_ENABLED", True):
        raise RedisDisabledError(
            f"Redis disabled for worker (REDIS_ENABLED=False). "
            f"Only Redis-FREE workers may set this. Worker: {getattr(settings, 'APP_NAME', '?')}"
        )
    from workers_common.redis import RedisManager

    return get_or_create(
        "redis:default",
        lambda: RedisManager(
            redis_url=settings.REDIS_URL,
            max_connections=getattr(settings, "REDIS_MAX_CONNECTIONS_PER_THREAD", 8),
            decode_responses=getattr(settings, "REDIS_DECODE_RESPONSES", True),
            socket_timeout=getattr(settings, "REDIS_SOCKET_TIMEOUT", 10.0),
            socket_connect_timeout=getattr(settings, "REDIS_SOCKET_CONNECT_TIMEOUT", 5.0),
            health_check_interval=getattr(settings, "REDIS_HEALTH_CHECK_INTERVAL", 30),
            retry_on_timeout=getattr(settings, "REDIS_RETRY_ON_TIMEOUT", True),
        ),
    )


async def dispose_thread_resources() -> None:
    """Close all managers owned by the *current thread* (reverse insertion order).

    Called by :func:`workers_common.async_bridge.dispose_thread_loop` before the
    loop is closed, so pooled connections are released cleanly. Safe to call when
    nothing has been created (no-op).
    """
    reg = getattr(_store, "registry", None)
    if not reg:
        return
    for obj in reversed(list(reg.values())):
        close = getattr(obj, "close", None)
        if close is None:
            continue
        try:
            if inspect.iscoroutinefunction(close):
                await close()
            else:
                close()
        except Exception:  # noqa: BLE001 — teardown must not raise
            pass
    _store.registry = {}

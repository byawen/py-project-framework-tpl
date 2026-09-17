"""指标上报器 — 每个 Celery 消费进程内跑一个 daemon 线程。

采集内容（每 METRICS_INTERVAL_SECONDS 秒一次）：
1. backlog：LLEN 各监听队列（连 broker redis，队列实际所在 db）。
2. active：celery.worker.state.active_requests 本进程在跑任务数（本地内存直读）。
3. 心跳：per-instance 心跳 key（实例存活观测 + gateway 实例数统计）。

监听队列来源（与 ENABLED_WORKERS 联动，不冲突）：调用方传入的 queue_names 已是
ENABLED_WORKERS 过滤后实际消费队列 - 剔除项（默认 "*" 自动剔除 beat schedule 派生的
周期投递轻队列），未启用的 worker 的队列不在其中，避免误报积压触发无效扩容。
新增 worker/队列自动纳入，无需维护白名单。

写入共享 Redis（REDIS_URL，与 worker 业务 redis 同 db，gateway 也读这个 db）：
- wio:m:backlog:<queue>            <llen>   EX <ttl>   （全局值，多进程覆盖无害）
- wio:m:active:<hostname>:<scope>  <count>  EX <ttl>   （per 进程，死进程 TTL 自愈）
- wio:m:instance:<hostname>:<scope> <ts>    EX <ttl>   （心跳，实例数统计）

gateway /worker-metrics 端点 SCAN wio:m:active:* / wio:m:backlog:* 聚合后输出。

fail-safe：
- LLEN 单队列失败 → 跳过该队列（不写，留旧值）。
- active 读失败 → 跳过（留旧值）。
- Redis 不可达 → 本轮跳过，下一轮重试；TTL 到期后 gateway 端 age/ok 反映。
- 线程内任何异常不外抛，不影响业务任务执行。
"""
from __future__ import annotations

import logging
import os
import socket
import threading
import time
from typing import TYPE_CHECKING

from redis import Redis
from redis.exceptions import RedisError

if TYPE_CHECKING:
    from celery import Celery

logger = logging.getLogger(__name__)

# per-instance key 前缀（与 gateway cache_reader 对齐）。tag 由 MetricsReporter.app_tag
# 注入：wio:m:<tag>:backlog/active/instance/pod，使多 SAE 应用指标互不污染。
_PREFIX = "wio:m"


def _hostname() -> str:
    """稳定的主机标识（用于 per-instance key）。

    多实例 SAE 下每个 pod 的 hostname 不同；同一 pod 内多个消费进程用 pid 区分。
    """
    return socket.gethostname() or "unknown"


class MetricsReporter:
    """单进程指标上报器。每个 Celery 消费进程持有一个实例。

    在 daemon 线程内周期采集，写共享 Redis。全同步，无 async 桥接。
    """

    def __init__(
        self,
        cache_redis_url: str,
        broker_redis_url: str,
        queue_names: list[str],
        interval_seconds: int = 30,
        ttl_seconds: int = 90,
        active_scope: str = "",
        app_tag: str = "default",
    ) -> None:
        """
        Args:
            cache_redis_url: 共享缓存 redis（REDIS_URL），写 per-instance key。
            broker_redis_url: broker redis（CELERY_BROKER_URL），LLEN 读队列积压。
            queue_names: 需上报 backlog 的重队列清单。
            interval_seconds: 采集周期（秒）。
            ttl_seconds: per-instance key TTL（≥ 3 × interval，防采集间隙过期）。
            active_scope: 本进程上报 active 的作用域标识（如 queue 名 + pid），
                          用于 per-instance key 去重。
            app_tag: per-app 指标隔离 tag（METRICS_APP_TAG）。key 形如
                     wio:m:<tag>:backlog:<queue>。默认 "default" 兼容单进程模式。
        """
        self._cache_url = cache_redis_url
        self._broker_url = broker_redis_url
        self._queue_names = list(queue_names)
        self._interval = max(5, int(interval_seconds))
        self._ttl = max(self._interval * 3, int(ttl_seconds))
        self._active_scope = active_scope or f"{os.getpid()}"
        self._hostname = _hostname()
        self._tag = app_tag or "default"
        self._cache: Redis | None = None  # 写 per-instance key
        self._broker: Redis | None = None  # LLEN 读队列
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ── per-app key 构造（tag 注入前缀，与 gateway cache_reader 对齐）──

    def _k_backlog(self, queue: str) -> str:
        return f"{_PREFIX}:{self._tag}:backlog:{queue}"

    def _k_active(self, scope_key: str) -> str:
        return f"{_PREFIX}:{self._tag}:active:{scope_key}"

    def _k_instance(self, scope_key: str) -> str:
        return f"{_PREFIX}:{self._tag}:instance:{scope_key}"

    def _k_pod(self) -> str:
        """per-pod 心跳 key：同 pod 所有进程 hostname 相同 → 自动收敛为 1 key/pod。
        gateway 计 distinct hostnames 即得 wio_pod_count{app}（真 pod 数，非进程数）。"""
        return f"{_PREFIX}:{self._tag}:pod:{self._hostname}"

    # ── redis 连接（懒创建，daemon 线程内首次用时建）──

    def _cache_client(self) -> Redis:
        if self._cache is None:
            self._cache = Redis.from_url(
                self._cache_url, decode_responses=True,
                socket_timeout=5.0, socket_connect_timeout=5.0,
            )
        return self._cache

    def _broker_client(self) -> Redis:
        if self._broker is None:
            self._broker = Redis.from_url(
                self._broker_url, decode_responses=True,
                socket_timeout=5.0, socket_connect_timeout=5.0,
            )
        return self._broker

    # ── 生命周期 ──

    def start(self) -> None:
        """启动 daemon 上报线程。幂等：重复调用只起一个线程。"""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="wio-metrics-reporter",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "MetricsReporter started: host=%s scope=%s interval=%ds ttl=%ds queues=%d",
            self._hostname, self._active_scope, self._interval, self._ttl,
            len(self._queue_names),
        )

    def stop(self) -> None:
        """停止上报线程。"""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3.0)
        # 关闭 redis 连接
        for client in (self._cache, self._broker):
            if client is not None:
                try:
                    client.close()
                except Exception:  # noqa: BLE001
                    pass

    # ── 主循环 ──

    def _run(self) -> None:
        # 首轮立刻采，之后按 interval
        while not self._stop.wait(self._interval):
            try:
                self._collect_once()
            except Exception as exc:  # noqa: BLE001
                # 线程内任何异常都吞掉，不能影响业务进程
                logger.debug("MetricsReporter collect error: %s", exc)

    def _collect_once(self) -> None:
        """一轮采集：backlog + active + 心跳，写共享 Redis。"""
        ts = int(time.time())
        pipe_ops: list[tuple[str, str, int]] = []  # (key, value, ttl)

        # 1. backlog（LLEN broker redis）—— 全局值，多进程覆盖无害
        try:
            broker = self._broker_client()
            for q in self._queue_names:
                try:
                    n = broker.llen(q)
                except RedisError as exc:
                    logger.debug("LLEN %s failed: %s", q, exc)
                    continue
                pipe_ops.append((self._k_backlog(q), str(int(n)), self._ttl))
        except Exception as exc:  # noqa: BLE001
            logger.debug("backlog collect error: %s", exc)

        # 2. active（本进程本地内存直读）
        active_count = self._read_local_active()

        # 3. 心跳 + active（per-instance key，TTL 自愈）+ per-pod 心跳（真 pod 数）
        scope_key = f"{self._hostname}:{self._active_scope}"
        if active_count is not None:
            pipe_ops.append(
                (self._k_active(scope_key), str(int(active_count)), self._ttl)
            )
        pipe_ops.append(
            (self._k_instance(scope_key), str(ts), self._ttl)
        )
        # per-pod：同 pod 所有进程写同一 key（hostname 相同），自动收敛为 1 key/pod
        pipe_ops.append((self._k_pod(), str(ts), self._ttl))

        if not pipe_ops:
            return

        # pipeline 批量写（任一失败下一轮重试，不影响业务）
        try:
            cache = self._cache_client()
            pipe = cache.pipeline(transaction=False)
            for key, val, ttl in pipe_ops:
                pipe.set(key, val, ex=ttl)
            pipe.execute()
        except RedisError as exc:
            logger.debug("metrics cache write failed: %s", exc)
        except Exception as exc:  # noqa: BLE001
            logger.debug("metrics cache write error: %s", exc)

    # ── active 本地读取 ──

    def _read_local_active(self) -> int | None:
        """读本进程在跑任务数（celery.worker.state.active_requests）。

        worker_ready 信号触发时本进程是 WorkController（threads 池 / prefork 主控）；
        worker_process_init 触发时是 prefork pool worker 孙进程。
        两者都有 celery.worker.state 可用，且是进程级状态。

        返回 None 表示读取不可用（不写 active key，留旧值）。
        """
        try:
            from celery.worker import state as worker_state
            active = getattr(worker_state, "active_requests", None)
            if active is None:
                return None
            # active_requests 是 set[Request]，长度即本进程在跑任务数
            try:
                return len(active)
            except TypeError:
                # 某些 celery 版本可能返回其它容器
                return None
        except Exception:  # noqa: BLE001
            return None


# ── Celery 信号挂载入口 ──

_reporters: list[MetricsReporter] = []
_reporters_lock = threading.Lock()


def install_metrics_reporter(
    celery_app: "Celery",
    cache_redis_url: str,
    broker_redis_url: str,
    queue_names: list[str],
    interval_seconds: int = 30,
    ttl_seconds: int = 90,
    app_tag: str = "default",
) -> None:
    """在 Celery app 上挂载 MetricsReporter，每个消费进程一个上报线程。

    策略：直接 spawn（不依赖 worker_ready 信号）。install_metrics_reporter 在
    _run_worker 内、worker_main() 调用前执行，此刻本进程已是消费进程主体（threads
    池）或即将 fork pool worker 的主控（prefork）。直接起线程，周期采集 active +
    心跳 + backlog，写共享 Redis。

    信号兜底（仅 prefork）：prefork 池下 worker_main 会再次 fork 出 pool worker 孙
    进程，孙进程是真正执行任务、持有 active_requests 的进程。主控进程直接起的
    reporter 读到的 active 恒为 0（它不跑任务），所以额外注册 worker_process_init
    信号，在每个孙进程 fork 后再起一个 reporter，读孙进程的 active。threads 池不
    fork，无孙进程，主控直接起的 reporter 即覆盖。worker_ready 信号在 prefork 下
    也会触发一次为 WorkController，但主控已直接起过，_spawn_reporter 幂等去重不会
    重复。

    app_tag：per-app 指标隔离 tag（METRICS_APP_TAG），写 key 时注入前缀，
    使多 SAE 应用指标互不污染。默认 "default"。

    幂等：_spawn_reporter 按 scope+hostname 去重，信号偶尔重触发无害。
    """
    # 直接为本进程起一个 reporter（覆盖 threads 池 + prefork 主控）
    scope = f"wc:{_hostname()}:{os.getpid()}"
    _spawn_reporter(scope, cache_redis_url, broker_redis_url,
                    queue_names, interval_seconds, ttl_seconds, app_tag)

    # prefork 孙进程兜底：worker_main 再次 fork 出的 pool worker 起一个 reporter
    from celery.signals import worker_process_init

    @worker_process_init.connect
    def _on_process_init(**kwargs):
        hostname = kwargs.get("hostname") or _hostname()
        scope = f"pw:{hostname}:{os.getpid()}"
        _spawn_reporter(scope, cache_redis_url, broker_redis_url,
                        queue_names, interval_seconds, ttl_seconds, app_tag)


def _spawn_reporter(
    scope: str,
    cache_redis_url: str,
    broker_redis_url: str,
    queue_names: list[str],
    interval_seconds: int,
    ttl_seconds: int,
    app_tag: str = "default",
) -> None:
    """创建并启动一个 MetricsReporter（幂等防同 scope 重复创建）。"""
    with _reporters_lock:
        # 防同 scope 重复注册（信号偶尔重触发）
        for r in _reporters:
            if r._active_scope == scope and r._hostname == _hostname():
                return
        reporter = MetricsReporter(
            cache_redis_url=cache_redis_url,
            broker_redis_url=broker_redis_url,
            queue_names=queue_names,
            interval_seconds=interval_seconds,
            ttl_seconds=ttl_seconds,
            active_scope=scope,
            app_tag=app_tag,
        )
        _reporters.append(reporter)
    reporter.start()

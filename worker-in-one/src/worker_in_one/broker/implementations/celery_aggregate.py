"""Celery 聚合 Broker 实现

把多个 worker 的 handlers 注册到同一个 Celery App，并按队列 fork 独立
子进程运行 worker_main，确保各队列拥有独立并发槽、独立 kombu 连接、互不抢占。

架构（per-queue process isolation）：
  旧: 一个 worker_main 消费所有队列，concurrency 个槽共享 → 慢队列饿死快队列
  新: 每个 queue fork 一个子进程，各自 worker_main(--queues=Q) → 队列隔离

为什么用多进程而非多线程：
  kombu 的 Redis transport 不是线程安全的（_channels set / poll()），
  多个 WorkController 线程共享同一个 Celery App 的连接池会触发
  "concurrent poll() invocation" 和 "Set changed size during iteration"。
  fork 后每个子进程有独立的 kombu hub 和连接池，彻底隔离。
"""

import logging
import multiprocessing
import os
import threading
from typing import TYPE_CHECKING, Any, Callable

from celery import Celery

from worker_in_one.broker.base import AggregateBroker
from workers_common.logging import reinit_file_logging

if TYPE_CHECKING:
    from worker_in_one.broker.spec import WorkerSpec
    from worker_in_one.config import Settings

_log = logging.getLogger(__name__)


class _CeleryRegisterAdapter:
    """把聚合 Celery App 适配为各 worker 期望的"类 BaseBroker"对象。

    各 worker 的 register_all_handlers(broker) 只调用 broker.register_handler(topic, handler)，
    此适配器将其映射为 celery_app.task(name=topic, bind=True)(handler)。
    """

    def __init__(self, app: Celery) -> None:
        self._app = app

    def register_handler(self, topic: str, handler: Callable, **task_opts) -> None:
        self._app.task(name=topic, bind=True, **task_opts)(handler)

    def start(self) -> None:  # pragma: no cover
        pass

    def stop(self) -> None:  # pragma: no cover
        pass

    def send_task(self, topic: str, payload: dict[str, Any], **kwargs) -> Any:  # pragma: no cover
        return None


class CeleryAggregateBroker(AggregateBroker):
    """Celery 聚合实现：多 worker 共享单个 Celery App。

    启动时为每个队列 fork 一个子进程，各自调用 worker_main 消费指定队列，
    拥有独立的并发槽和 kombu 连接，互不抢占。
    """

    broker_type = "celery"
    requires_main_thread = True

    def __init__(self, settings: "Settings") -> None:
        self.settings = settings
        self._app: Celery | None = None
        self._worker_names: list[str] = []
        self._queues: list[str] = []
        self._processes: list[multiprocessing.Process] = []
        self._stop_event = threading.Event()
        self._mp_ctx = multiprocessing.get_context("fork")
        # 收集各 worker 的 beat schedule（合并后注入 app.conf）
        self._beat_schedule: dict[str, dict] = {}

    # ── Celery App 懒初始化 ──

    @property
    def app(self) -> Celery:
        """获取聚合 Celery App（懒初始化）。"""
        if self._app is None:
            self._app = Celery(
                self.settings.APP_NAME,
                broker=self.settings.CELERY_BROKER_URL,
                backend=self.settings.CELERY_BROKER_RESULT_BACKEND,
            )
            self._app.conf.update(
                worker_loglevel=self.settings.CELERY_WORKER_LOGLEVEL,
                task_serializer=self.settings.CELERY_TASK_SERIALIZER,
                result_serializer=self.settings.CELERY_RESULT_SERIALIZER,
                accept_content=[x.strip() for x in self.settings.CELERY_ACCEPT_CONTENT.split(",")],
                timezone=self.settings.CELERY_TIMEZONE,
                enable_utc=self.settings.CELERY_ENABLE_UTC,
                task_track_started=True,
                task_acks_late=True,
                worker_prefetch_multiplier=self.settings.CELERY_WORKER_PREFETCH_MULTIPLIER,
                # Redis broker visibility_timeout，必须 > 最长 task time_limit，
                # 否则长任务还在跑就被 Redis 重投给另一 worker，占多个并发槽
                broker_transport_options={
                    "visibility_timeout": getattr(
                        self.settings, "CELERY_BROKER_VISIBILITY_TIMEOUT_S", 3600
                    )
                },
                # 全局 task 超时兜底（未在 per-topic retry config 单独设超时的 topic 走此值）
                task_time_limit=getattr(self.settings, "CELERY_TASK_TIME_LIMIT", 600),
                task_soft_time_limit=getattr(
                    self.settings, "CELERY_TASK_SOFT_TIME_LIMIT", 540),
                worker_hijack_root_logger=False,
                worker_redirect_stdouts=True,
                worker_redirect_stdouts_level="INFO",
                beat_schedule_filename=getattr(self.settings, "CELERY_BEAT_SCHEDULE_FILENAME", "celerybeat-schedule"),
                # OOM 防护：worker 回收 + worker_lost 时 reject 重入队
                worker_max_tasks_per_child=getattr(self.settings, "CELERY_WORKER_MAX_TASKS_PER_CHILD", 50),
                worker_max_memory_per_child=getattr(self.settings, "CELERY_WORKER_MAX_MEMORY_PER_CHILD", 2_000_000),
                task_reject_on_worker_lost=getattr(self.settings, "CELERY_TASK_REJECT_ON_WORKER_LOST", True),
                # ── 禁用 pidbox 远程控制面（多 SAE 应用共用 broker 必需）──
                # 5 个 SAE 应用共用同一个 CELERY_BROKER_URL 且 Celery app 名相同
                # （APP_NAME=worker-in-one），pidbox 控制面完全合一：任一 pod 的
                # control.shutdown() 广播（PreStop `celery control shutdown` / 旧代码 /
                # 滚动重启）会打到全部应用的全部 worker → `Got shutdown from remote`
                # 级联杀全场，只剩部分 app 勉强存活写指标。
                # 禁用后 worker 不消费任何 pidbox 控制命令（shutdown/revoke/inspect），
                # 广播无处落地 → 级联杀不可能发生；同时消灭 mingle `sync with` 跨应用
                # 互相发现噪声。本系统不依赖 pidbox：停 worker 靠 SIGTERM→proc.terminate
                # （本 pod scoped），active 指标走 celery.worker.state 本地内存直读，
                # 跨应用投递靠 send_task（走 broker 队列非 pidbox），均不受影响。
                worker_enable_remote_control=False,
                worker_mingle=False,
                worker_gossip=False,
            )
        return self._app

    # ── per-queue 并发解析 ──

    def _parse_queue_concurrency(self) -> dict[str, int]:
        """读取 CELERY_QUEUE_CONCURRENCY 配置。

        返回 {queue_name: concurrency}。
        未列出的队列回退到 CELERY_WORKER_CONCURRENCY。

        配置项已是 dict 类型（pydantic-settings 从 env JSON 字符串自动解析），
        这里只做取值与合法性过滤，不再解析 JSON。
        """
        raw = getattr(self.settings, "CELERY_QUEUE_CONCURRENCY", None) or {}
        if not isinstance(raw, dict):
            _log.warning(
                "CELERY_QUEUE_CONCURRENCY is not a dict (%s), using default",
                type(raw).__name__,
            )
            return {}
        return {str(k): int(v) for k, v in raw.items() if v > 0}

    def _parse_queue_pool(self) -> dict[str, str]:
        """读取 CELERY_QUEUE_POOL 配置（方案 D：每队列自选执行池）。

        返回 {queue_name: pool_type}，合法值 threads / prefork / solo。
        未列出的队列回退 prefork。

        若 CELERY_USE_THREADS_POOL feature flag 为 False（一键回滚），
        直接返回空 dict → 全部回退 prefork，等价现状。

        配置项已是 dict 类型（pydantic-settings 从 env JSON 字符串自动解析），
        这里只做取值与合法性过滤，不再解析 JSON。
        """
        if not getattr(self.settings, "CELERY_USE_THREADS_POOL", True):
            _log.info(
                "CELERY_USE_THREADS_POOL is False — all queues fall back to prefork"
            )
            return {}
        raw = getattr(self.settings, "CELERY_QUEUE_POOL", None) or {}
        if not isinstance(raw, dict):
            _log.warning(
                "CELERY_QUEUE_POOL is not a dict (%s), all queues fall back to prefork",
                type(raw).__name__,
            )
            return {}
        valid = {"threads", "prefork", "solo"}
        result = {str(k): str(v) for k, v in raw.items() if str(v) in valid}
        if result:
            _log.info("Per-queue pool override: %s", result)
        return result

    # ── 派生 beat 驱动的轻队列 ──

    def _derive_beat_queues(self) -> set[str]:
        """从 self._beat_schedule 解析 beat 周期投递的目标队列集合。

        每个 beat entry 的队列来源（优先级）：
        1. entry["options"]["queue"] — beat entry 显式指定的队列
        2. task_routes[entry["task"]]["queue"] — 通过任务路由解析的队列

        这些队列由 beat 周期性投递，LLEN 不可能持续为 0，报给 SAE 弹性会误触发
        扩容，故在 METRICS_QUEUE_EXCLUDE_PATTERNS="*" 时自动剔除。
        """
        beat_queues: set[str] = set()
        routes = self.app.conf.task_routes or {}
        for entry in self._beat_schedule.values():
            if not isinstance(entry, dict):
                continue
            q = (entry.get("options") or {}).get("queue")
            if not q:
                task_name = entry.get("task")
                route = routes.get(task_name) if task_name else None
                if isinstance(route, dict):
                    q = route.get("queue")
            if q:
                beat_queues.add(q)
        if beat_queues:
            _log.info(
                "Derived beat-driven light queues (%d): %s",
                len(beat_queues), sorted(beat_queues),
            )
        return beat_queues

    # ── 注册 worker ──

    def register_worker(self, spec: "WorkerSpec") -> None:
        """把单个 worker 的 handlers 注册到聚合 Celery App。

        Celery task 注册时内部通过 exec() 生成优化 tracer，
        函数签名字符串会泄露到 stdout。在此阶段静默 stdout 避免垃圾输出。
        """
        import contextlib, io

        adapter = _CeleryRegisterAdapter(self.app)
        with contextlib.redirect_stdout(io.StringIO()):
            spec.register_handlers(adapter)
        self._worker_names.append(spec.name)

        ws = spec.settings
        if ws is not None:
            # 把 worker 的 task_routes 合并到 app.conf
            # worker 内部 current_app.send_task() 依赖路由投递到正确队列，
            # 否则新发送的任务会落到 Celery 默认 celery queue（无 worker 消费）
            routes = getattr(ws, "CELERY_TASK_ROUTES", None) or {}
            if routes:
                merged = dict(self.app.conf.task_routes or {})
                merged.update(routes)
                self.app.conf.task_routes = merged

            default_q = getattr(ws, "CELERY_TASK_DEFAULT_QUEUE", None)
            if default_q and default_q not in self._queues:
                self._queues.append(default_q)

            queues_raw = getattr(ws, "CELERY_TASK_QUEUES", "")
            if queues_raw:
                for q in queues_raw.split(","):
                    q = q.strip()
                    if q and q not in self._queues:
                        self._queues.append(q)
            else:
                routes = getattr(ws, "CELERY_TASK_ROUTES", None) or {}
                for route in routes.values():
                    if not isinstance(route, dict):
                        continue
                    # queue：本 task 默认路由队列
                    if route.get("queue"):
                        q = route["queue"]
                        if q not in self._queues:
                            self._queues.append(q)
                    # queues：本 task 额外服务的物理车道（同一 handler 多队列消费），
                    # 逗号分隔逐一附加（CELERY_TASK_QUEUES 留空时由此派生提取）
                    extra = route.get("queues", "")
                    if isinstance(extra, str) and extra:
                        for q in extra.split(","):
                            q = q.strip()
                            if q and q not in self._queues:
                                self._queues.append(q)

            # ── 收集 Beat 定时调度 ──
            # 各 worker 通过 CELERY_BEAT_ENABLE + CELERY_BEAT_SCHEDULE 声明定时任务，
            # 聚合后由一个 fork 进程携带 --beat 运行调度器。
            beat_enabled = getattr(ws, "CELERY_BEAT_ENABLE", False)
            beat_schedule = getattr(ws, "CELERY_BEAT_SCHEDULE", None) or {}
            if beat_enabled and beat_schedule:
                self._beat_schedule.update(beat_schedule)
                _log.info(
                    "Beat schedule collected from worker %s: %s",
                    spec.name, list(beat_schedule.keys()),
                )

    # ── 启动 / 停止 ──

    def start(self) -> None:
        """为每个队列 fork 子进程运行 worker_main，主线程阻塞直到停止。

        若有收集到 Beat schedule 且 CELERY_BEAT_ENABLED=True，额外 fork 一个独立
        Beat 进程运行 app.Beat().run()（不再嵌入队列 worker，避免强制载体队列
        prefork）。多节点幂等由各 handler 内部分布式锁保证。
        """
        if not self._queues:
            _log.warning("No queues registered, CeleryAggregateBroker idle")
            return

        queue_conc = self._parse_queue_concurrency()
        queue_pool = self._parse_queue_pool()
        default_conc = self.settings.CELERY_WORKER_CONCURRENCY
        default_pool = "threads"  # 未配置的队列走 threads， 进程 prefork
        loglevel = self.settings.CELERY_WORKER_LOGLEVEL
        app_name = self.settings.APP_NAME
        app = self.app  # 确保所有 handler 已注册

        # 日志配置（fork 后子进程需用这些参数重建文件日志线程）
        log_file_enabled = getattr(self.settings, "LOG_FILE", False)
        log_dir = getattr(self.settings, "LOG_DIR", "./logs")
        log_file_max_bytes = getattr(self.settings, "LOG_FILE_MAX_BYTES", 100 * 1024 * 1024)
        log_file_backup_count = getattr(self.settings, "LOG_FILE_BACKUP_COUNT", 100)

        # ── 注入合并后的 Beat 调度计划 ──
        # CELERY_BEAT_ENABLED 默认 True 保持单实例现状；多实例部署时只在
        # 指定实例设 True，其余 False，避免多 Beat 同时触发（handler 层
        # leader 锁仍作兜底）。
        beat_enabled = getattr(self.settings, "CELERY_BEAT_ENABLED", True)
        use_beat = bool(self._beat_schedule) and beat_enabled
        if self._beat_schedule and not beat_enabled:
            _log.info(
                "CELERY_BEAT_ENABLED is False — Beat scheduler disabled on this instance "
                "(%d beat entries collected but not scheduled): %s",
                len(self._beat_schedule), list(self._beat_schedule.keys()),
            )
        if use_beat:
            from workers_common.broker import resolve_schedule
            resolved = {}
            for name, entry in self._beat_schedule.items():
                resolved[name] = {
                    **entry,
                    "schedule": resolve_schedule(entry["schedule"]),
                }
            app.conf.beat_schedule = resolved
            _log.info(
                "Beat schedule injected (%d entries): %s",
                len(resolved), list(resolved.keys()),
            )

        # ── 派生 beat 驱动的轻队列集合（供 METRICS_QUEUE_EXCLUDE_PATTERNS="*" 自动剔除）──
        # beat 周期投递的队列（callback_notify/outbox.*/vimu_poll 等）LLEN 不可能持续
        # 为 0，报给 SAE 会误触发扩容。从 self._beat_schedule 派生这些队列：每个 beat
        # entry 的队列取 entry["options"]["queue"]，否则从 task_routes[entry["task"]]
        # 解析。beat schedule 从所有 CELERY_BEAT_ENABLE 的 worker 收集（与
        # CELERY_BEAT_ENABLED 全局开关无关），故非 beat 实例也能派生。
        self._beat_queues = self._derive_beat_queues()

        for i, queue in enumerate(self._queues):
            conc = queue_conc.get(queue, default_conc)
            pool_type = queue_pool.get(queue, default_pool)
            hostname = f"{app_name}@{queue.replace('.', '-')}"

            # fork 后子进程继承 app（含所有已注册 task），无需 pickle
            # 使用默认参数捕获当前迭代的值
            def _run_worker(
                _app=app, _queue=queue, _conc=conc,
                _pool=pool_type, _loglevel=loglevel, _hostname=hostname,
                _log_file_enabled=log_file_enabled,
                _log_dir=log_dir,
                _log_file_max_bytes=log_file_max_bytes,
                _log_file_backup_count=log_file_backup_count,
                _app_name=app_name,
                _settings=self.settings,
                _active_queues=list(self._queues),
                _beat_queues=set(self._beat_queues),
            ):
                import io, sys, contextlib
                print(
                    f"\n{'='*60}\n"
                    f"  Queue Worker starting\n"
                    f"  queue={_queue}  pool={_pool}  concurrency={_conc}  hostname={_hostname}\n"
                    f"{'='*60}\n",
                    flush=True,
                )
                # ── 第一层 fork：队列进程 ──
                # fork 只复制内存不复制线程：父进程的 QueueListener 线程
                # 在子进程内不存在，但 _state.file_queue 仍为非 None（内存复制），
                # 导致日志被投入队列却无人消费、永远不落盘。
                if _log_file_enabled:
                    reinit_file_logging(
                        service_name=f"{_app_name}-{_queue}",
                        log_dir=_log_dir,
                        log_file_max_bytes=_log_file_max_bytes,
                        log_file_backup_count=_log_file_backup_count,
                    )

                # ── 第二层 fork：Celery prefork pool worker ──
                # Celery worker_main 默认用 prefork pool，会再次 fork 出 N 个
                # pool worker 子进程执行任务。这些进程同样没有 QueueListener 线程，
                # 需要在 worker_process_init 信号中重建。
                # 用环境变量传递队列名，信号回调中据此生成正确的日志文件名。
                if _log_file_enabled:
                    import os as _os
                    _os.environ["_WI1_LOG_QUEUE"] = _queue
                    _os.environ["_WI1_LOG_APP_NAME"] = _app_name
                    _os.environ["_WI1_LOG_DIR"] = _log_dir or ""
                    _os.environ["_WI1_LOG_MAX_BYTES"] = str(_log_file_max_bytes)
                    _os.environ["_WI1_LOG_BACKUP_COUNT"] = str(_log_file_backup_count)

                    from celery.signals import worker_process_init
                    @worker_process_init.connect
                    def _reinit_log_in_pool_worker(**kwargs):
                        _q = _os.environ.get("_WI1_LOG_QUEUE", "unknown")
                        _a = _os.environ.get("_WI1_LOG_APP_NAME", "worker-in-one")
                        _d = _os.environ.get("_WI1_LOG_DIR", "./logs") or "./logs"
                        _mb = int(_os.environ.get("_WI1_LOG_MAX_BYTES", str(100 * 1024 * 1024)))
                        _bc = int(_os.environ.get("_WI1_LOG_BACKUP_COUNT", "100"))
                        reinit_file_logging(
                            service_name=f"{_a}-{_q}",
                            log_dir=_d,
                            log_file_max_bytes=_mb,
                            log_file_backup_count=_bc,
                        )

                # ── async bridge 进程级钩子（threads 与 prefork 都注册）──
                # - threads 队列：worker_shutdown/atexit 关闭本线程 loop + thread-local
                #   manager，释放池内连接（best-effort）。
                # - prefork 队列：worker_process_init 信号在每个 pool worker 孙进程 fork
                #   后触发，重置继承自父进程主线程的 thread-local（loop/manager 缓存），
                #   防止孙进程复用绑了已关闭 loop 的脏 manager。threads 下该信号不触发，无害。
                try:
                    from workers_common.async_bridge import install_shutdown_hook

                    install_shutdown_hook()
                except Exception:  # noqa: BLE001
                    pass

                # ── Prometheus 指标上报挂载 ──
                # 在 worker_main 前为本进程直接挂一个 MetricsReporter daemon 线程，
                # 周期采集 backlog + active + 心跳写共享 Redis。
                # 见 worker_in_one/metrics/reporter.py。
                #
                # 监听队列来源（与 ENABLED_WORKERS 联动，不冲突）：
                # _active_queues 已是 ENABLED_WORKERS 过滤后实际消费的队列全集
                # （start() 收集，未启用的 worker 的队列不在此列）。
                # METRICS_QUEUE_EXCLUDE_PATTERNS 控制剔除：
                # - "*"（默认）：自动剔除 _beat_queues（从 beat schedule 派生的周期投递
                #   轻队列 callback_notify/outbox/vimu_poll 等，其 LLEN 不可能持续为 0，
                #   会污染 SAE 弹性判定）。
                # - 显式正则（逗号分隔）：按正则匹配剔除（手动控制兜底）。
                # - 空串：不剔除，上报全部实际消费队列。
                # 新增 worker/队列自动纳入，无需维护白名单。
                try:
                    if getattr(_settings, "METRICS_ENABLED", True):
                        from worker_in_one.metrics.reporter import install_metrics_reporter

                        excl_raw = str(
                            getattr(_settings, "METRICS_QUEUE_EXCLUDE_PATTERNS", "*")
                        ).strip()
                        if excl_raw == "*":
                            # 自动：剔除 beat schedule 派生的周期投递队列
                            metrics_queues = [
                                q for q in _active_queues if q not in _beat_queues
                            ]
                        elif excl_raw:
                            # 显式正则黑名单
                            import re as _re
                            patterns = [
                                _re.compile(p.strip())
                                for p in excl_raw.split(",")
                                if p.strip()
                            ]
                            metrics_queues = [
                                q for q in _active_queues
                                if not any(p.search(q) for p in patterns)
                            ]
                        else:
                            metrics_queues = list(_active_queues)
                        install_metrics_reporter(
                            celery_app=_app,
                            cache_redis_url=_settings.REDIS_URL,
                            broker_redis_url=_settings.CELERY_BROKER_URL,
                            queue_names=metrics_queues,
                            interval_seconds=int(getattr(_settings, "METRICS_INTERVAL_SECONDS", 30)),
                            app_tag=str(getattr(_settings, "METRICS_APP_TAG", "default")),
                        )
                except Exception:  # noqa: BLE001
                    _log.warning("MetricsReporter install failed, metrics disabled", exc_info=True)

                # Celery trace 模块通过 exec() 生成优化 tracer，
                # 源码字符串会泄露到 stdout。在 worker_main 期间静默 stdout。
                with open("/dev/null", "w") as _devnull, contextlib.redirect_stdout(_devnull):
                    worker_argv = [
                        "worker",
                        f"--loglevel={_loglevel}",
                        f"--pool={_pool}",
                        f"--concurrency={_conc}",
                        f"--queues={_queue}",
                        f"--hostname={_hostname}",
                    ]
                    _app.worker_main(worker_argv)

            proc = self._mp_ctx.Process(
                target=_run_worker,
                name=f"celery-{queue}-{pool_type}",
                daemon=True,
            )
            proc.start()
            self._processes.append(proc)
            _log.info(
                "Queue worker process started: queue=%s, pool=%s, concurrency=%d, hostname=%s, pid=%d",
                queue, pool_type, conc, hostname, proc.pid,
            )

        _log.info(
            "All queue worker processes started: %s",
            {
                q: {
                    "concurrency": queue_conc.get(q, default_conc),
                    "pool": queue_pool.get(q, default_pool),
                }
                for q in self._queues
            },
        )

        # ── 独立 Beat 进程 ──
        # Beat 与队列消费解耦：单独 fork 一个进程跑 app.Beat().run()，不再嵌入
        # 第一个队列 worker（旧实现强制该 worker prefork，导致 6 个应用的 beat 载体
        # 队列无法用 threads，DB 连接 15/子进程 vs threads 5/线程）。Beat 职责仅为
        # 周期性 send_task 到 broker，独立进程不影响任何队列消费；多实例重复投递由
        # 各 handler 内 Redis leader 锁去重。
        if use_beat:
            beat_filename = getattr(
                self.settings, "CELERY_BEAT_SCHEDULE_FILENAME", "celerybeat-schedule"
            )

            def _run_beat(
                _app=app, _loglevel=loglevel, _beat_filename=beat_filename,
                _log_file_enabled=log_file_enabled, _log_dir=log_dir,
                _log_file_max_bytes=log_file_max_bytes,
                _log_file_backup_count=log_file_backup_count, _app_name=app_name,
            ):
                print(
                    f"\n{'='*60}\n"
                    f"  Beat scheduler starting (independent process)\n"
                    f"  schedule={_beat_filename}\n"
                    f"{'='*60}\n",
                    flush=True,
                )
                # fork 不复制父进程日志线程，子进程需重建（与 _run_worker 同理）
                if _log_file_enabled:
                    reinit_file_logging(
                        service_name=f"{_app_name}-beat",
                        log_dir=_log_dir,
                        log_file_max_bytes=_log_file_max_bytes,
                        log_file_backup_count=_log_file_backup_count,
                    )
                # 确保父目录存在 — Celery shelve.open 不会自动创建目录
                beat_dir = os.path.dirname(_beat_filename)
                if beat_dir:
                    os.makedirs(beat_dir, exist_ok=True)
                # 清理残留的旧 schedule 文件 — SAE 实例重启时 temp/ 可能残留
                # 空/损坏的 dbm 文件，shelve.open 报 "db type could not be determined"
                for _suffix in ("", ".db", ".dat", ".bak", ".dir"):
                    _f = _beat_filename + _suffix
                    if os.path.exists(_f):
                        try:
                            os.remove(_f)
                        except OSError:
                            pass
                # 运行 Beat 调度器（阻塞，直到收到 SIGTERM）
                _app.Beat(loglevel=_loglevel, schedule=_beat_filename).run()

            beat_proc = self._mp_ctx.Process(
                target=_run_beat,
                name="celery-beat",
                daemon=True,
            )
            beat_proc.start()
            self._processes.append(beat_proc)
            _log.info(
                "Independent Beat process started: pid=%d, schedule=%s",
                beat_proc.pid, beat_filename,
            )

        self._stop_event.wait()

    def stop(self) -> None:
        """停止所有子进程。"""
        self._stop_event.set()

        for proc in self._processes:
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=10)
                if proc.is_alive():
                    _log.warning("Process did not terminate, killing: pid=%d", proc.pid)
                    proc.kill()
                    proc.join(timeout=5)

        # 不调 self._app.control.shutdown()：那是 pidbox 广播，会打到共享 broker 上其它
        # SAE 应用 / 其它 pod 的全部 worker（5 应用共用一个 CELERY_BROKER_URL），一次缩容
        # 或滚动发布就会级联杀全场。上方 proc.terminate() 已对本 pod 子进程发 SIGTERM，
        # 子进程各自走 Celery warm shutdown，scope 仅限本 pod，安全。
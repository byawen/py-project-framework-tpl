"""Celery Broker 通用实现

基于 Celery 的消息队列实现，使用 Redis 作为 Broker 和 Result Backend。

构造方式：
  1. 显式 CeleryBrokerConfig: CeleryBroker(CeleryBrokerConfig(url=..., options={...}))
     — 用于一个 worker 持有多个不同 broker 的场景
  2. 从 settings: CeleryBroker(settings)
     — 兼容旧接口，getattr 读取 CELERY_BROKER_URL / CELERY_TASK_ROUTES 等字段
"""

import os
from typing import Any, Callable

from celery import Celery

from workers_common.broker.base import BaseBroker
from workers_common.broker.broker_config import CeleryBrokerConfig


def _get(obj, name, default=None):
    """从 CeleryBrokerConfig（.options dict）或 settings（getattr）统一取值"""
    if isinstance(obj, CeleryBrokerConfig):
        if name in ("CELERY_BROKER_URL",):
            return obj.url
        if name in ("CELERY_BROKER_RESULT_BACKEND",):
            return obj.result_backend
        if name in ("APP_NAME",):
            return getattr(obj, "app_name", "worker")
        return obj.options.get(name, default)
    return getattr(obj, name, default)


def resolve_schedule(schedule: Any) -> Any:
    """将纯数据 schedule 描述转为 Celery 调度对象

    支持格式：
      - int / float          → 原样传递（Celery 视为 interval seconds）
      - {"crontab": {...}}   → celery.schedules.crontab(**kwargs)
      - {"timedelta": {...}} → datetime.timedelta(**kwargs)
      - 其他                 → 原样传递（兼容直接传入 crontab/timedelta 对象）

    此函数被 CeleryBroker（单 worker 模式）和 CeleryAggregateBroker
    （worker-in-one 聚合模式）共用，保证 schedule 解析行为一致。
    """
    if isinstance(schedule, dict):
        if "crontab" in schedule:
            from celery.schedules import crontab
            return crontab(**schedule["crontab"])
        if "timedelta" in schedule:
            from datetime import timedelta
            return timedelta(**schedule["timedelta"])
    return schedule


class CeleryBroker(BaseBroker):
    """Celery 消息队列实现（通用，可被各 worker 复用）"""

    def __init__(self, config: CeleryBrokerConfig | Any):
        """初始化

        Args:
            config: CeleryBrokerConfig 或 settings 对象（getattr 风格）
        """
        self._config = config
        self._app: Celery | None = None
        self._handlers: dict[str, Callable] = {}

    @property
    def app(self) -> Celery:
        """获取 Celery App 实例（懒初始化）"""
        if self._app is None:
            c = self._config
            self._app = Celery(
                _get(c, "APP_NAME", "worker"),
                broker=_get(c, "CELERY_BROKER_URL", "redis://localhost:6379/1"),
                backend=_get(c, "CELERY_BROKER_RESULT_BACKEND", "redis://localhost:6379/2"),
            )

            # 读取 worker 可自定义的队列路由
            task_routes = _get(c, "CELERY_TASK_ROUTES", None)
            default_queue = _get(c, "CELERY_TASK_DEFAULT_QUEUE", "default")

            self._app.conf.update(
                # 序列化
                task_serializer=_get(c, "CELERY_TASK_SERIALIZER", "json"),
                result_serializer=_get(c, "CELERY_RESULT_SERIALIZER", "json"),
                accept_content=[
                    x.strip() for x in _get(c, "CELERY_ACCEPT_CONTENT", "json").split(",")
                ],
                # 时区
                timezone=_get(c, "CELERY_TIMEZONE", "Asia/Shanghai"),
                enable_utc=_get(c, "CELERY_ENABLE_UTC", True),
                # 队列路由
                task_default_queue=default_queue,
                task_routes=task_routes or {},
                # 并发（长任务，逐一消费）
                worker_concurrency=_get(c, "CELERY_WORKER_CONCURRENCY", 4),
                worker_loglevel=_get(c, "CELERY_WORKER_LOGLEVEL", "info"),
                worker_prefetch_multiplier=_get(c, "CELERY_WORKER_PREFETCH_MULTIPLIER", 1),
                # 超时
                task_time_limit=_get(c, "CELERY_TASK_TIME_LIMIT", 600),
                task_soft_time_limit=_get(c, "CELERY_TASK_SOFT_TIME_LIMIT", 540),
                # 可靠性
                task_track_started=True,
                task_acks_late=_get(c, "CELERY_TASK_ACKS_LATE", True),
                task_reject_on_worker_lost=_get(c, "CELERY_TASK_REJECT_ON_WORKER_LOST", True),
                # 不让 Celery 劫持 root logger，避免自定义日志被降级为 WARNING
                worker_hijack_root_logger=False,
                # Beat 持久化文件路径（避免在项目根目录生成 celerybeat-schedule）
                beat_schedule_filename=_get(c, "CELERY_BEAT_SCHEDULE_FILENAME", "celerybeat-schedule"),
            )
        return self._app

    def register_handler(self, topic: str, handler: Callable, **task_opts) -> None:
        """注册 Celery 任务处理器

        Args:
            topic: 任务名（也是路由 key）
            handler: 处理函数
            **task_opts: 覆盖全局 Celery 配置的 per-task 参数
                        如 max_retries=5, default_retry_delay=60
        """
        self._handlers[topic] = handler
        self.app.task(
            name=topic,
            bind=True,
            max_retries=task_opts.pop("max_retries",
                                      _get(self._config, "CELERY_TASK_MAX_RETRIES", 3)),
            default_retry_delay=task_opts.pop("default_retry_delay",
                                              _get(self._config, "CELERY_TASK_RETRY_DELAY", 30)),
            **task_opts,
        )(handler)

    def start(self, extra_args: list[str] | None = None) -> None:
        """启动 Celery Worker

        自动处理 Celery Beat 定时调度：
        - 若 CELERY_BEAT_ENABLE=True 且 CELERY_BEAT_SCHEDULE 非空，
          自动注入 beat_schedule 到 app.conf 并添加 --beat 启动参数。
        - 多节点幂等由各 handler 内部分布式锁保证。

        Args:
            extra_args: 额外的 Celery worker CLI 参数（如 ["--without-gossip"]）
        """
        from importlib import import_module

        config = self._config
        # 从 settings 推断 worker 包名；CeleryBrokerConfig 没有 __class__.__module__
        if isinstance(config, CeleryBrokerConfig):
            handlers_pkg = config.options.get("HANDLERS_MODULE", "handlers")
            try:
                handlers_mod = import_module(handlers_pkg)
                handlers_mod.register_all_handlers(self)
            except (ImportError, AttributeError):
                pass
        else:
            # Settings 通常在 {worker}.foundation.config；handlers 在 {worker}.handlers
            module = config.__class__.__module__
            parent = module.rsplit(".", 1)[0]
            candidates = [f"{parent}.handlers"]
            if parent.endswith(".foundation"):
                candidates.append(f"{parent[: -len('.foundation')]}.handlers")
            if module.count(".") >= 2:
                candidates.append(f"{module.rsplit('.', 2)[0]}.handlers")
            for handlers_pkg in candidates:
                try:
                    handlers_mod = import_module(handlers_pkg)
                    handlers_mod.register_all_handlers(self)
                    break
                except (ImportError, AttributeError):
                    continue

        # ── Celery Beat 定时调度注入 ──
        beat_enabled = _get(self._config, "CELERY_BEAT_ENABLE", False)
        beat_schedule = _get(self._config, "CELERY_BEAT_SCHEDULE", None) or {}
        use_beat = beat_enabled and bool(beat_schedule)
        if use_beat:
            # 将纯数据描述（{"crontab": {...}} / {"timedelta": {...}} / int）
            # 转为 Celery 调度对象后注入
            resolved = {}
            for name, entry in beat_schedule.items():
                resolved[name] = {
                    **entry,
                    "schedule": resolve_schedule(entry["schedule"]),
                }
            self.app.conf.beat_schedule = resolved

        queues = _get(self._config, "CELERY_TASK_QUEUES", None)
        if not queues:
            routes = _get(self._config, "CELERY_TASK_ROUTES", None) or {}
            default_queue = _get(self._config, "CELERY_TASK_DEFAULT_QUEUE", "default")
            queue_set = {default_queue}
            for route in routes.values():
                if isinstance(route, dict) and route.get("queue"):
                    queue_set.add(route["queue"])
            queues = ",".join(sorted(queue_set))
        queue_args = f"--queues={queues}" if queues else ""

        worker_argv = [
            "worker",
            f"--loglevel={_get(self._config, 'CELERY_WORKER_LOGLEVEL', 'info')}",
            f"--concurrency={_get(self._config, 'CELERY_WORKER_CONCURRENCY', 4)}",
        ]
        if use_beat:
            worker_argv.append("--beat")
            # 显式传 --schedule，命令行优先级高于 app.conf，避免 Celery 默认覆盖到根目录
            beat_filename = _get(self._config, "CELERY_BEAT_SCHEDULE_FILENAME", "celerybeat-schedule")
            # 确保父目录存在 — Celery shelve.open 不会自动创建目录
            beat_dir = os.path.dirname(beat_filename)
            if beat_dir:
                os.makedirs(beat_dir, exist_ok=True)
            worker_argv.append(f"--schedule={beat_filename}")
        if queue_args:
            worker_argv.append(queue_args)
        if extra_args:
            worker_argv.extend(extra_args)

        self.app.worker_main(worker_argv)

    def stop(self) -> None:
        """停止 Celery Worker"""
        self.app.control.shutdown()

    def send_task(self, topic: str, payload: dict[str, Any], **kwargs) -> Any:
        """发送 Celery 任务

        统一使用 kwargs 风格传递 payload（与 services_common.task_publisher 对齐）。
        worker handler 签名应为 def handler(self, **kwargs) 或 def handler(self, payload=None, **kwargs)。
        """
        delay = kwargs.pop("delay", None)
        queue = kwargs.pop("queue", None)
        send_kwargs: dict[str, Any] = {"kwargs": payload}
        if queue:
            send_kwargs["queue"] = queue
        if delay:
            send_kwargs["countdown"] = delay
        result = self.app.send_task(topic, **send_kwargs)
        return result.id

"""Celery TaskPublisher — 服务端任务派发

基于 Celery 的任务发布实现，使用 Redis 作为 Broker 和 Result Backend。
与 workers_common.broker.implementations.celery_broker (consumer 端) 共享
同一套配置约定（CELERY_BROKER_URL / CELERY_BROKER_RESULT_BACKEND / CELERY_TASK_ROUTES 等），
但职责分离：只管 send，不启动 worker 进程。

构造方式：
  1. 显式 CeleryBrokerConfig: CeleryTaskPublisher(CeleryBrokerConfig(url=..., options={...}))
     — 用于一个 service 持有多个不同 publisher 的场景
  2. 从 settings: CeleryTaskPublisher(settings)
     — 兼容旧接口，getattr 读取 CELERY_BROKER_URL / CELERY_TASK_ROUTES 等字段
"""

from typing import Any

from celery import Celery

from services_common.task_publisher.base import BaseTaskPublisher
from services_common.task_publisher.broker_config import CeleryBrokerConfig


def _get(obj, name, default=None):
    """从 CeleryBrokerConfig（.options dict）或 settings（getattr）统一取值"""
    if isinstance(obj, CeleryBrokerConfig):
        if name in ("CELERY_BROKER_URL",):
            return obj.url
        if name in ("CELERY_BROKER_RESULT_BACKEND",):
            return obj.result_backend
        if name in ("APP_NAME",):
            return getattr(obj, "app_name", "service")
        return obj.options.get(name, default)
    return getattr(obj, name, default)


class CeleryTaskPublisher(BaseTaskPublisher):
    """Celery 任务发布实现（通用，可被各 service 复用）"""

    def __init__(self, config: CeleryBrokerConfig | Any):
        """初始化

        Args:
            config: CeleryBrokerConfig 或 settings 对象（getattr 风格）
        """
        self._config = config
        self._app: Celery | None = None

    @property
    def app(self) -> Celery:
        """获取 Celery App 实例（懒初始化）"""
        if self._app is None:
            c = self._config
            self._app = Celery(
                _get(c, "APP_NAME", "service"),
                broker=_get(c, "CELERY_BROKER_URL", "redis://localhost:6379/1"),
                backend=_get(c, "CELERY_BROKER_RESULT_BACKEND", "redis://localhost:6379/2"),
            )

            # 队列路由 — 与 CeleryBroker 读取同一配置
            task_routes = _get(c, "CELERY_TASK_ROUTES", None)

            # 规范化 accept_content — config 存储为逗号分隔字符串（与 consumer 端一致）
            _accept_raw = _get(c, "CELERY_ACCEPT_CONTENT", "json")
            if isinstance(_accept_raw, str):
                accept_content = [x.strip() for x in _accept_raw.split(",")]
            else:
                accept_content = list(_accept_raw)

            self._app.conf.update(
                # 序列化
                task_serializer=_get(c, "CELERY_TASK_SERIALIZER", "json"),
                result_serializer=_get(c, "CELERY_RESULT_SERIALIZER", "json"),
                accept_content=accept_content,
                # 时区
                timezone=_get(c, "CELERY_TIMEZONE", "Asia/Shanghai"),
                enable_utc=_get(c, "CELERY_ENABLE_UTC", True),
                # 队列路由
                task_routes=task_routes or {},
            )
        return self._app

    def send(self, topic: str, payload: dict[str, Any], **kwargs) -> str:
        """派发单条 Celery 任务

        Args:
            topic: 任务名（对应 worker 端 register_handler 的 topic）
            payload: 任务载荷（以 kwargs 传递给 worker handler）
            **kwargs:
                queue: 目标队列（覆盖 task_routes 默认路由）
                delay: 延迟执行秒数
                priority: 优先级

        Returns:
            Celery AsyncResult.id
        """
        queue = kwargs.pop("queue", None)
        delay = kwargs.pop("delay", None)

        send_kwargs: dict[str, Any] = {"kwargs": payload}
        if queue:
            send_kwargs["queue"] = queue
        if delay:
            send_kwargs["countdown"] = delay

        result = self.app.send_task(topic, **send_kwargs)
        return result.id

    def send_batch(self, tasks: list[tuple[str, dict[str, Any]]], **kwargs) -> list[str]:
        """批量派发 Celery 任务"""
        return [self.send(topic, payload, **kwargs) for topic, payload in tasks]


__all__ = ["CeleryTaskPublisher"]
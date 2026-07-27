"""TaskPublisherManager — 多 publisher 路由管理

一个 service 可同时持有多个不同类型的 publisher（如 celery + pubsub + rabbitmq），
由 manager 统一管理实例生命周期和路由。

使用方式：
    manager = TaskPublisherManager()
    manager.register("celery", settings)   # settings 是 WorkersSettings 实例

    # 按 broker_name 派发
    manager.send("celery", topic="worker.process", payload={...})

    # 或直接获取 publisher 实例
    celery_pub = manager.get_publisher("celery")
    celery_pub.send(topic=..., payload=...)
"""

from typing import Any

from services_common.config import WorkersSettings
from services_common.task_publisher.base import BaseTaskPublisher
from services_common.task_publisher.factory import PUBLISHER_REGISTRY, create_publisher


class TaskPublisherManager:
    """管理多个 TaskPublisher 实例，按 broker_name 路由派发

    可被 injector 直接绑定：binder.bind(TaskPublisherManager, scope=singleton)
    各 service module 在构造时显式 register。
    """

    def __init__(self):
        """初始化空 manager，不自动注册任何 publisher"""
        self._publishers: dict[str, BaseTaskPublisher] = {}

    def register(self, name: str, config: WorkersSettings) -> BaseTaskPublisher:
        """注册一个 publisher 实例

        根据 name 从 PUBLISHER_REGISTRY 查找实现类，用 config 构造实例。
        name 同时作为 registry key 和路由 key。

        Args:
            name: publisher 名称 + 中间件类型标识（如 "celery" / "pubsub"），
                  必须存在于 PUBLISHER_REGISTRY 中
            config: WorkersSettings 实例（或其子类），实现类内部通过 getattr 取所需字段

        Returns:
            创建的 publisher 实例
        """
        publisher = create_publisher(broker_type=name, config=config)
        self._publishers[name] = publisher
        return publisher

    def get_publisher(self, name: str) -> BaseTaskPublisher:
        """获取指定名称的 publisher 实例"""
        if name not in self._publishers:
            available = ", ".join(self._publishers.keys()) or "(empty)"
            raise KeyError(f"Publisher '{name}' not registered. Available: {available}")
        return self._publishers[name]

    def send(self, broker_name: str, topic: str, payload: dict[str, Any], **kwargs) -> str:
        """通过指定 broker 派发任务

        Args:
            broker_name: publisher 名称（register 时指定的 name）
            topic: 任务主题/队列名
            payload: 任务载荷
            **kwargs: 额外参数（queue, delay 等）

        Returns:
            任务 ID
        """
        return self.get_publisher(broker_name).send(topic, payload, **kwargs)

    def send_batch(
        self, broker_name: str, tasks: list[tuple[str, dict[str, Any]]], **kwargs
    ) -> list[str]:
        """通过指定 broker 批量派发任务"""
        return self.get_publisher(broker_name).send_batch(tasks, **kwargs)

    @property
    def registered_names(self) -> list[str]:
        """已注册的 publisher 名称列表"""
        return list(self._publishers.keys())


__all__ = ["TaskPublisherManager"]
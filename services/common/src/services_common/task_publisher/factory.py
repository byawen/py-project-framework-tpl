"""任务发布工厂

根据 broker_type 创建对应的 TaskPublisher 实例。
与 workers_common.broker.factory 对称，共享 PUBLISHER_REGISTRY 设计。

使用方式：
  create_publisher(broker_type="celery", config=settings)
  — settings 是 WorkersSettings（或其子类），实现类内部通过 getattr 取所需字段。

新增中间件只需在 PUBLISHER_REGISTRY 中注册。
各 service 可通过 extend_publisher_registry() 追加本地实现。
"""

from typing import TYPE_CHECKING

from services_common.config import WorkersSettings

if TYPE_CHECKING:
    from services_common.task_publisher.base import BaseTaskPublisher

# Publisher 注册表 — 新增中间件只需在此添加映射
PUBLISHER_REGISTRY: dict[str, str] = {
    "celery": "services_common.task_publisher.implementations.celery_publisher.CeleryTaskPublisher",
    # 后续扩展示例：
    # "pubsub": "services_common.task_publisher.implementations.pubsub_publisher.PubSubPublisher",
    # "kafka": "services_common.task_publisher.implementations.kafka_publisher.KafkaPublisher",
}


def _import_class(dotted_path: str):
    """动态导入类"""
    module_path, class_name = dotted_path.rsplit(".", 1)
    import importlib

    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def extend_publisher_registry(extra: dict[str, str]) -> None:
    """扩展 Publisher 注册表（供 service 追加本地实现）

    Args:
        extra: {broker_type: dotted_class_path} 映射
    """
    PUBLISHER_REGISTRY.update(extra)


def create_publisher(
    *,
    broker_type: str,
    config: WorkersSettings,
    registry: dict[str, str] | None = None,
) -> "BaseTaskPublisher":
    """创建 TaskPublisher 实例

    Args:
        broker_type: 中间件类型（如 "celery" / "pubsub"），必须存在于 registry 中
        config: WorkersSettings 实例（或其子类），实现类内部通过 getattr 取所需字段
        registry: 可选覆盖注册表（默认使用全局 PUBLISHER_REGISTRY）
    """
    reg = registry if registry is not None else PUBLISHER_REGISTRY

    if broker_type not in reg:
        supported = ", ".join(reg.keys())
        raise ValueError(f"Unknown broker_type '{broker_type}'. Supported types: {supported}")

    cls_path = reg[broker_type]
    publisher_cls = _import_class(cls_path)
    return publisher_cls(config)


__all__ = ["PUBLISHER_REGISTRY", "create_publisher", "extend_publisher_registry"]
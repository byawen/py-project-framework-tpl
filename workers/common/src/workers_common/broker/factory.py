"""Broker 工厂

根据 broker_type 创建对应的 Broker 实例。
新增中间件只需在 BROKER_REGISTRY 中注册即可。

使用方式：
  create_broker(broker_type="celery", config=settings)
  — settings 是 WorkersSettings（或其子类），实现类内部通过 getattr 取所需字段。

每个 worker 的 broker/__init__.py 中可扩展 BROKER_REGISTRY
以注册 worker 本地特有的实现。
"""

from typing import TYPE_CHECKING

from workers_common.config import WorkersSettings

if TYPE_CHECKING:
    from workers_common.broker.base import BaseBroker

# Broker 注册表 — 新增中间件只需在此添加映射
# worker 可通过 extend_broker_registry() 追加本地实现
BROKER_REGISTRY: dict[str, str] = {
    "celery": "workers_common.broker.implementations.celery_broker.CeleryBroker",
    # 后续扩展示例：
    # "rabbitmq": "workers_common.broker.implementations.rabbitmq_broker.RabbitMQBroker",
}


def _import_class(dotted_path: str):
    """动态导入类"""
    module_path, class_name = dotted_path.rsplit(".", 1)
    import importlib

    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def extend_broker_registry(extra: dict[str, str]) -> None:
    """扩展 Broker 注册表（供 worker 追加本地实现）

    Args:
        extra: {broker_type: dotted_class_path} 映射
    """
    BROKER_REGISTRY.update(extra)


def create_broker(
    *,
    broker_type: str,
    config: WorkersSettings,
    registry: dict[str, str] | None = None,
) -> "BaseBroker":
    """根据配置创建 Broker 实例

    Args:
        broker_type: 中间件类型（如 "celery" / "pubsub"），必须存在于 registry 中
        config: WorkersSettings 实例（或其子类），实现类内部通过 getattr 取所需字段
        registry: 可选覆盖注册表（默认使用全局 BROKER_REGISTRY）
    """
    reg = registry if registry is not None else BROKER_REGISTRY

    if broker_type not in reg:
        supported = ", ".join(reg.keys())
        raise ValueError(f"Unknown broker_type '{broker_type}'. Supported types: {supported}")

    cls_path = reg[broker_type]
    broker_cls = _import_class(cls_path)
    return broker_cls(config)


__all__ = ["BROKER_REGISTRY", "create_broker", "extend_broker_registry"]
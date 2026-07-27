"""聚合 Broker 工厂

根据 broker_type 创建对应的 AggregateBroker 实例。
新增中间件聚合支持只需在 AGGREGATE_BROKER_REGISTRY 中注册。
"""
import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from worker_in_one.broker.base import AggregateBroker
    from worker_in_one.foundation.config import Settings

# 聚合 Broker 注册表 — 新增中间件只需在此添加映射
AGGREGATE_BROKER_REGISTRY: dict[str, str] = {
    "celery": "worker_in_one.broker.implementations.celery_aggregate.CeleryAggregateBroker",
    # 后续扩展示例（取消注释并实现对应类即可启用）:
    # "rabbitmq": "worker_in_one.broker.implementations.rabbitmq_aggregate.RabbitMQAggregateBroker",
    # "pubsub": "worker_in_one.broker.implementations.pubsub_aggregate.PubSubAggregateBroker",
    # "kafka": "worker_in_one.broker.implementations.kafka_aggregate.KafkaAggregateBroker",
}


def _import_class(dotted_path: str):
    """动态导入类。"""
    module_path, class_name = dotted_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def create_aggregate_broker(broker_type: str, settings: "Settings") -> "AggregateBroker":
    """根据类型创建聚合 Broker 实例。"""
    if broker_type not in AGGREGATE_BROKER_REGISTRY:
        supported = ", ".join(AGGREGATE_BROKER_REGISTRY.keys())
        raise ValueError(
            f"Unknown broker_type '{broker_type}'. Supported types: {supported}"
        )

    cls_path = AGGREGATE_BROKER_REGISTRY[broker_type]
    broker_cls = _import_class(cls_path)
    return broker_cls(settings)


__all__ = ["AGGREGATE_BROKER_REGISTRY", "create_aggregate_broker"]
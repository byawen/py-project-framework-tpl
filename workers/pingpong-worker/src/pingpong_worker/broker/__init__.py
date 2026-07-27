"""Broker 模块 — 转发 workers_common 通用实现

本 worker 无自定义 broker 实现，直接复用 workers_common.broker。
如需新增本地 broker 实现（如 RabbitMQ），在此扩展 BROKER_REGISTRY。
"""

from workers_common.broker import (
    BROKER_REGISTRY,
    BaseBroker,
    create_broker,
    extend_broker_registry,
    get_broker,
)

__all__ = [
    "BaseBroker",
    "BROKER_REGISTRY",
    "create_broker",
    "extend_broker_registry",
    "get_broker",
]

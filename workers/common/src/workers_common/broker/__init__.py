"""Broker 模块

提供消息队列的抽象和工厂模式，支持多种 Broker 实现。
与 services_common.task_publisher（生产端）对称：
  services/common/task_publisher  → 生产任务或消息（send）
  workers/common/broker           → 消费任务或消息（register_handler + start）

支持一个 worker 同时消费多个不同类型的 broker（如 celery + pubsub），
由 BrokerManager 统一路由。
"""

from workers_common.broker.base import BaseBroker
from workers_common.broker.broker_config import CeleryBrokerConfig
from workers_common.broker.factory import (
    BROKER_REGISTRY,
    create_broker,
    extend_broker_registry,
)
from workers_common.broker.implementations.celery_broker import resolve_schedule
from workers_common.broker.manager import BrokerManager

__all__ = [
    "BaseBroker",
    "CeleryBrokerConfig",
    "BrokerManager",
    "BROKER_REGISTRY",
    "create_broker",
    "extend_broker_registry",
    "resolve_schedule",
]
"""Task Publisher 模块

提供服务端任务/消息发布的抽象和工厂模式，与 workers_common.broker（消费端）对称。
共享同一套配置约定，但职责分离：
  services/common/task_publisher  → 生产任务或消息（send）
  workers/common/broker           → 消费任务或消息（register_handler + start）

支持一个 service 同时持有多个不同类型的 publisher（如 celery + pubsub 并存），
由 TaskPublisherManager 统一路由。
"""

from services_common.task_publisher.base import BaseTaskPublisher
from services_common.task_publisher.broker_config import CeleryBrokerConfig
from services_common.task_publisher.factory import (
    PUBLISHER_REGISTRY,
    create_publisher,
    extend_publisher_registry,
)
from services_common.task_publisher.manager import TaskPublisherManager

__all__ = [
    "BaseTaskPublisher",
    "CeleryBrokerConfig",
    "TaskPublisherManager",
    "PUBLISHER_REGISTRY",
    "create_publisher",
    "extend_publisher_registry",
]
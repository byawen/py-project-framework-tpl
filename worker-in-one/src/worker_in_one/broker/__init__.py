"""Worker-in-One 聚合 Broker 模块

提供聚合多 worker 的 broker 抽象、工厂与运行编排，支持多种中间件类型并发运行。
"""
from worker_in_one.broker.base import AggregateBroker
from worker_in_one.broker.factory import (
    AGGREGATE_BROKER_REGISTRY,
    create_aggregate_broker,
)
from worker_in_one.broker.runner import BrokerRunner
from worker_in_one.broker.spec import WorkerSpec

__all__ = [
    "AggregateBroker",
    "AGGREGATE_BROKER_REGISTRY",
    "create_aggregate_broker",
    "BrokerRunner",
    "WorkerSpec",
]
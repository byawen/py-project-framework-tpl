"""WorkerSpec - 被聚合 worker 的描述

workers_registry() 为每个加载成功的 worker 产出一个 WorkerSpec，
BrokerRunner 据此按 broker_type 分组并驱动消费。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


# worker 暴露的 handler 注册函数：接收"类 BaseBroker"对象，
# 内部调用 obj.register_handler(topic, handler)。
# 复用各 worker 已有的 register_all_handlers(broker)。
HandlerRegisterFn = Callable[[Any], None]


@dataclass
class WorkerSpec:
    """单个被聚合 worker 的描述。

    Attributes:
        name           : worker 名称（用于日志/分组诊断）
        broker_type    : 该 worker 使用的中间件类型（celery / rabbitmq / pubsub ...）
        register_handlers: 把该 worker 的 handlers 注册进 broker 的函数
        settings       : 该 worker 的配置实例（聚合 broker 初始化时可能需要）
        required       : 是否为必需的 worker（必需的 worker 始终启动，即使未在 ENABLED_WORKERS 中指定）
    """

    name: str
    broker_type: str
    register_handlers: HandlerRegisterFn
    settings: Any = None
    required: bool = False


__all__ = ["WorkerSpec", "HandlerRegisterFn"]
"""Broker 抽象层

定义消息队列的统一接口，支持多种实现（Celery、RabbitMQ、PubSub 等）。
所有具体 Broker 实现必须继承 BaseBroker 并实现其抽象方法。
"""

from abc import ABC, abstractmethod
from typing import Any, Callable


class BaseBroker(ABC):
    """消息队列抽象基类

    所有 Broker 实现的统一接口。新增中间件只需:
    1. 在 broker/implementations/ 下新建实现类，继承 BaseBroker
    2. 在 broker/factory.py 的 BROKER_REGISTRY 中注册
    """

    @abstractmethod
    def start(self, extra_args: list[str] | None = None) -> None:
        """启动 Broker 消费者

        Args:
            extra_args: 传递给底层 CLI 的额外参数（如 celery worker_main 的选项）
        """
        pass

    @abstractmethod
    def stop(self) -> None:
        """停止 Broker 消费者"""
        pass

    @abstractmethod
    def register_handler(self, topic: str, handler: Callable, **task_opts) -> None:
        """注册消息处理器

        Args:
            topic: 消息主题/队列名
            handler: 消息处理回调函数
            **task_opts: 任务级覆盖参数（如 max_retries, default_retry_delay 等）
                        由具体实现透传给底层任务注册框架
        """
        pass

    @abstractmethod
    def send_task(self, topic: str, payload: dict[str, Any], **kwargs) -> Any:
        """发送任务到消息队列

        Args:
            topic: 消息主题/队列名
            payload: 任务载荷
            **kwargs: 额外参数（如 delay, priority 等）

        Returns:
            任务结果或任务 ID
        """
        pass


__all__ = ["BaseBroker"]

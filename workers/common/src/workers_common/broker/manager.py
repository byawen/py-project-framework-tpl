"""BrokerManager — 多 broker 消费端管理（与 TaskPublisherManager 对称）

一个 worker 可同时消费多个不同类型的 broker（如 celery + pubsub），
由 manager 统一管理实例生命周期和 handler 注册。

使用方式：
    manager = BrokerManager()
    manager.register("celery", settings)  # settings 是 WorkersSettings 实例

    # 注册 handler
    manager.register_handler("celery", "worker.process", handler_func)

    # 启动消费者（阻塞）
    manager.start("celery")

    # 或启动全部
    manager.start_all()
"""

from typing import Callable

from workers_common.broker.base import BaseBroker
from workers_common.broker.factory import BROKER_REGISTRY, create_broker
from workers_common.config import WorkersSettings


class BrokerManager:
    """管理多个 BaseBroker 实例，统一 handler 注册和生命周期控制"""

    def __init__(self):
        """初始化空 manager，不自动注册任何 broker"""
        self._brokers: dict[str, BaseBroker] = {}

    def register(self, name: str, config: WorkersSettings) -> BaseBroker:
        """注册一个 broker 实例

        根据 name 从 BROKER_REGISTRY 查找实现类，用 config 构造实例。
        name 同时作为 registry key 和路由 key。

        Args:
            name: broker 名称 + 中间件类型标识（如 "celery" / "pubsub"），
                  必须存在于 BROKER_REGISTRY 中
            config: WorkersSettings 实例（或其子类），实现类内部通过 getattr 取所需字段

        Returns:
            创建的 broker 实例
        """
        broker = create_broker(broker_type=name, config=config)
        self._brokers[name] = broker
        return broker

    def get_broker(self, name: str) -> BaseBroker:
        """获取指定名称的 broker 实例"""
        if name not in self._brokers:
            available = ", ".join(self._brokers.keys()) or "(empty)"
            raise KeyError(f"Broker '{name}' not registered. Available: {available}")
        return self._brokers[name]

    def register_handler(self, broker_name: str, topic: str, handler: Callable) -> None:
        """向指定 broker 注册消息处理器"""
        self.get_broker(broker_name).register_handler(topic, handler)

    def start(self, broker_name: str, extra_args: list[str] | None = None) -> None:
        """启动指定 broker 的消费者（阻塞）

        注意：对于 Celery 等 blocking broker，会阻塞当前进程。
        多 broker 场景应使用 start_all() 在独立线程中启动非阻塞 broker，
        或将不同 broker 部署到不同 worker 进程。

        Args:
            broker_name: 已注册的 broker 名称
            extra_args: 传递给 broker 实现的额外 CLI 参数
        """
        self.get_broker(broker_name).start(extra_args=extra_args)

    def start_all(self, extra_args: list[str] | None = None) -> None:
        """启动所有已注册 broker 的消费者

        注意：当前实现仅启动第一个 broker（Celery worker_main 会阻塞）。
        多 broker 并行消费需要各自独立进程，或未来引入非阻塞 broker 实现。

        Args:
            extra_args: 传递给 broker 实现的额外 CLI 参数
        """
        if not self._brokers:
            return
        first_name = next(iter(self._brokers))
        self._brokers[first_name].start(extra_args=extra_args)

    def stop(self, broker_name: str | None = None) -> None:
        """停止指定 broker，或全部停止"""
        if broker_name:
            self.get_broker(broker_name).stop()
        else:
            for broker in self._brokers.values():
                broker.stop()

    def stop_all(self) -> None:
        """停止所有已注册 broker"""
        for broker in self._brokers.values():
            broker.stop()

    @property
    def registered_names(self) -> list[str]:
        """已注册的 broker 名称列表"""
        return list(self._brokers.keys())


__all__ = ["BrokerManager"]
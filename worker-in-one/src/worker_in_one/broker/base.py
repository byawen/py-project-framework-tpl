"""Worker-in-One 聚合 Broker 抽象层

与单 worker 的 broker 抽象（pingpong_worker.broker）对偶：

  单 worker broker      : 一个进程消费"自己"的 handlers
  worker-in-one broker  : 一个进程聚合"多个 worker"的 handlers，按中间件类型分组消费

新增中间件聚合支持只需:
  1. 在 broker/implementations/ 下新建实现类，继承 AggregateBroker
  2. 在 broker/factory.py 的 AGGREGATE_BROKER_REGISTRY 中注册

设计原则:
  - handler 注册与消费启动解耦：先 register_worker() 收集所有 worker 的 handler，
    再 start() 启动消费
  - 同一 broker_type 的多个 worker 共享同一个 AggregateBroker 实例
  - 不同 broker_type 由 BrokerRunner 并发驱动
"""
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from worker_in_one.broker.spec import WorkerSpec


# worker 的 handler 注册函数签名：接收一个"类 BaseBroker"对象，
# 内部调用 obj.register_handler(topic, handler)
HandlerRegisterFn = Callable[[Any], None]


class AggregateBroker(ABC):
    """聚合 Broker 抽象基类

    一个实例负责一种中间件类型（celery / rabbitmq / pubsub ...），
    聚合并消费归属于该类型的所有 worker 的 handlers。
    """

    #: 该实现对应的 broker 类型标识（在 WorkerSpec 中显式指定）
    broker_type: str = ""

    #: 是否要求在主线程运行（如 Celery 依赖主线程信号处理）。
    #: BrokerRunner 会把 requires_main_thread=True 的 broker 放在前台主线程，
    #: 其余放入 daemon 线程并发运行。
    requires_main_thread: bool = False

    @abstractmethod
    def register_worker(self, spec: "WorkerSpec") -> None:
        """登记一个 worker：把它的 handlers 注册进本聚合 Broker。

        Args:
            spec: worker 描述，包含 name 与 register_handlers 注册函数
        """
        ...

    @abstractmethod
    def start(self) -> None:
        """启动消费（阻塞直到收到停止信号）。"""
        ...

    @abstractmethod
    def stop(self) -> None:
        """优雅停止消费。"""
        ...


__all__ = ["AggregateBroker", "HandlerRegisterFn"]
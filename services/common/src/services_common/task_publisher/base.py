"""任务发布抽象层

定义服务端（producer）派发任务/消息的统一接口。
与 workers_common.broker（consumer 端）对称，共享同一套配置约定，
但职责分离：publisher 只管 send，不关心 start/stop/register_handler。
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseTaskPublisher(ABC):
    """任务发布抽象基类

    所有 publisher 实现的统一接口。新增中间件只需:
    1. 在 task_publisher/implementations/ 下新建实现类，继承 BaseTaskPublisher
    2. 在 factory.py 的 PUBLISHER_REGISTRY 中注册
    """

    @abstractmethod
    def send(self, topic: str, payload: dict[str, Any], **kwargs) -> str:
        """派发单条任务

        Args:
            topic: 任务主题/队列名（对应 worker 端 register_handler 的 topic）
            payload: 任务载荷（以 kwargs 风格传递给 worker handler）
            **kwargs: 额外参数（queue, delay, priority 等）

        Returns:
            任务 ID
        """
        ...

    @abstractmethod
    def send_batch(self, tasks: list[tuple[str, dict[str, Any]]], **kwargs) -> list[str]:
        """批量派发任务

        Args:
            tasks: [(topic, payload), ...] 列表
            **kwargs: 额外参数（对所有任务生效）

        Returns:
            任务 ID 列表
        """
        ...


__all__ = ["BaseTaskPublisher"]
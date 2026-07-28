"""派发 Echo 异步任务命令模块

将 echo 任务投递到 pingpong-worker 队列，由 worker 异步消费。
投递即本用例的全部职责（无业务逻辑下沉），故归 commands 而非 service。
"""
from dataclasses import dataclass
from injector import inject

from pingpong_service.app.infrastructure.task_dispatcher import EchoTaskDispatcher
from pingpong_service.foundation.logging import get_logger

logger = get_logger(__name__)


@dataclass
class DispatchEchoTaskResult:
    """派发 echo 任务命令执行结果"""
    task_id: str
    message: str


class DispatchEchoTaskCommand:
    """派发 echo 异步任务命令处理器"""

    @inject
    def __init__(self, dispatcher: EchoTaskDispatcher):
        self.dispatcher = dispatcher

    async def execute(self, message: str) -> DispatchEchoTaskResult:
        """执行派发 echo 任务命令

        Args:
            message: 要投递给 worker 的消息内容

        Returns:
            包含 task_id 与原 message 的结果
        """
        logger.info(
            "派发 echo 任务开始",
            operation="pingpong.echo_task.dispatch.start",
            message=message,
        )

        task_id = self.dispatcher.dispatch(message)

        logger.info(
            "派发 echo 任务成功",
            operation="pingpong.echo_task.dispatch.success",
            task_id=task_id,
            message=message,
        )

        return DispatchEchoTaskResult(
            task_id=task_id,
            message=message,
        )

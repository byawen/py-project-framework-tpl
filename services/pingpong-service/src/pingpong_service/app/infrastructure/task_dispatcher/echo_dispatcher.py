"""Echo 异步任务派发器

封装 services_common.task_publisher.TaskPublisherManager，将 echo 任务
路由到 pingpong-worker 消费的队列。参照 content-ops-service 的
VideoTaskDispatcher（app/infrastructure/celery_client.py）。

topic / queue / broker_name 均从 Settings 读取（PIPO_ECHO_* 配置项），
与 pingpong-worker 侧 PIPO_ECHO_TASK_TOPIC 逐字对齐：
  - topic（两段）：pingpong_worker.echo_task
  - queue（三段）：pingpong_worker.echo.process
"""
from injector import inject

from services_common.task_publisher import TaskPublisherManager
from pingpong_service.foundation.config import Settings


class EchoTaskDispatcher:
    """Echo 任务派发器

    封装 TaskPublisherManager，将 echo 任务路由到指定 broker。
    当前使用 celery publisher，未来可扩展到其他 broker 而不影响业务代码。
    """

    @inject
    def __init__(self, manager: TaskPublisherManager, settings: Settings):
        self._manager = manager
        self._topic = settings.PIPO_ECHO_TASK_TOPIC
        self._queue = settings.PIPO_ECHO_TASK_QUEUE
        self._broker_name = settings.PIPO_ECHO_BROKER_NAME

    def dispatch(self, message: str) -> str:
        """派发单条 echo 任务，返回 task id

        Args:
            message: 要投递给 worker 的消息内容

        Returns:
            Celery task id
        """
        return self._manager.send(
            broker_name=self._broker_name,
            topic=self._topic,
            payload={"message": message},
            queue=self._queue,
        )

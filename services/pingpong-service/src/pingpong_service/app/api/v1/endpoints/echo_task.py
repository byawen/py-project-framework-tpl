"""Echo 异步任务 API 端点

接收 HTTP 请求，投递 echo 任务到 pingpong-worker 队列异步消费。
"""
from fastapi import APIRouter, Depends
from services_common.response import success, DataResponse

from pingpong_service.foundation.container import get_injector
from pingpong_service.foundation.logging import get_logger
from pingpong_service.app.api.v1.schemas.echo_task import (
    EchoTaskRequest,
    EchoTaskResponse,
)
from pingpong_service.app.application.commands.dispatch_echo_task import DispatchEchoTaskCommand

router = APIRouter(prefix="/echo-task", tags=["echo-task"])
logger = get_logger(__name__)


def get_dispatch_echo_task_command() -> DispatchEchoTaskCommand:
    """获取 DispatchEchoTaskCommand 实例"""
    return get_injector().get(DispatchEchoTaskCommand)


@router.post("", response_model=DataResponse[EchoTaskResponse])
async def dispatch_echo_task(
    request: EchoTaskRequest,
    command: DispatchEchoTaskCommand = Depends(get_dispatch_echo_task_command),
) -> DataResponse[EchoTaskResponse]:
    """投递 echo 异步任务 - 将 message 发送到 pingpong-worker 队列"""
    logger.info("Echo task dispatch requested", message=request.message)
    result = await command.execute(request.message)
    response_data = EchoTaskResponse(
        task_id=result.task_id,
        message=result.message,
    )
    return success(data=response_data, message="Echo task dispatched")

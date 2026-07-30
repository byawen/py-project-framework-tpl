"""Echo 任务数据模式模块

Echo 异步任务相关请求/响应 DTO
"""
from pydantic import BaseModel, Field
from services_common.response import DataResponse


class EchoTaskRequest(BaseModel):
    """Echo 任务请求 schema"""
    message: str = Field(..., min_length=1, max_length=255, description="要投递给 worker 的消息内容")


class EchoTaskResponse(BaseModel):
    """Echo 任务响应 schema"""
    task_id: str = Field(..., description="Celery 任务 ID")
    message: str = Field(..., description="投递的消息内容")


class EchoTaskDataResponse(DataResponse[EchoTaskResponse]):
    """Echo 任务 DataResponse 包装响应"""
    pass

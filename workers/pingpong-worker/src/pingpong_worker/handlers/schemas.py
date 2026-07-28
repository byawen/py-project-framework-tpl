"""handler 边界数据模型

handler 专用 payload/result 模型（等价 service 的 api/v1/schemas）。
入站 payload 在 handler 队列边界处转成 Payload 模型再传给 application；
返回值用 Result 模型 .model_dump() 序列化进 result backend，禁止手拼 dict。
"""
from pydantic import BaseModel, Field


class EchoTaskPayload(BaseModel):
    """echo 任务入站 payload 校验模型"""
    message: str = Field(..., min_length=1, max_length=255, description="要处理的消息内容")


class EchoTaskResult(BaseModel):
    """echo 任务返回结果（序列化进 result backend）"""
    pong_id: str
    message: str

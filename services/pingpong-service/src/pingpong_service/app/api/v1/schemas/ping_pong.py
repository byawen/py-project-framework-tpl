"""Ping Pong 数据模式模块

Ping/Pong 相关请求/响应 DTO
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field
from services_common.response import DataResponse


# ============== Ping DTOs ==============

class PingResponse(BaseModel):
    """Ping 响应 schema"""
    message: str = Field(..., description="Ping message")
    ping_id: Optional[str] = Field(None, description="Ping ID")
    created_at: Optional[datetime] = Field(None, description="Created at")


class PingDataResponse(DataResponse[PingResponse]):
    """Ping DataResponse 包装响应"""
    pass


# ============== Pong DTOs ==============

class PongRequest(BaseModel):
    """Pong 请求 schema"""
    data: str = Field(..., min_length=1, max_length=255, description="Pong data")


class PongResponse(BaseModel):
    """Pong 响应 schema"""
    data: str = Field(..., description="Pong data")
    pong_id: Optional[str] = Field(None, description="Pong ID")
    created_at: Optional[datetime] = Field(None, description="Created at")


class PongDataResponse(DataResponse[PongResponse]):
    """Pong DataResponse 包装响应"""
    pass

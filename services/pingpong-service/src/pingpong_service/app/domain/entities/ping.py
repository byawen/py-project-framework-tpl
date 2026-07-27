"""Ping 实体模块

Ping 聚合根 - 核心领域实体
"""
from datetime import datetime
from pydantic import BaseModel, Field


class Ping(BaseModel):
    """Ping 领域实体"""
    ping_id: str = Field(..., description="Ping ID")
    message: str = Field(..., description="Ping message")
    created_at: datetime = Field(default_factory=datetime.now, description="Created at")
    
    class Config:
        """Pydantic 配置"""
        from_attributes = True
    
    def update_message(self, message: str) -> None:
        """更新 ping 消息"""
        self.message = message


class Pong(BaseModel):
    """Pong 领域实体"""
    pong_id: str = Field(..., description="Pong ID")
    data: str = Field(..., description="Pong data")
    created_at: datetime = Field(default_factory=datetime.now, description="Created at")
    
    class Config:
        """Pydantic 配置"""
        from_attributes = True
    
    def update_data(self, data: str) -> None:
        """更新 pong 数据"""
        self.data = data

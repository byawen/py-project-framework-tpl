"""Pong 仓储接口模块

Pong 仓储接口 - 定义 Pong 实体的持久化操作
"""
from typing import Optional
from abc import ABC, abstractmethod
from pingpong_service.app.domain.entities.ping import Pong


class PongRepository(ABC):
    """Pong 仓储接口"""
    
    @abstractmethod
    async def get_by_id(self, pong_id: str) -> Optional[Pong]:
        """根据 ID 获取 Pong"""
        pass
    
    @abstractmethod
    async def create(self, pong: Pong) -> Pong:
        """创建 Pong"""
        pass
    
    @abstractmethod
    async def update(self, pong: Pong) -> Pong:
        """更新 Pong"""
        pass
    
    @abstractmethod
    async def delete(self, pong_id: str) -> None:
        """删除 Pong"""
        pass

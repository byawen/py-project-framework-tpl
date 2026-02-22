"""Ping 仓储接口模块

Ping 仓储接口 - 定义 Ping 实体的持久化操作
"""
from typing import Optional
from abc import ABC, abstractmethod
from pingpong_service.app.domain.entities.ping import Ping


class PingRepository(ABC):
    """Ping 仓储接口"""
    
    @abstractmethod
    async def get_by_id(self, ping_id: str) -> Optional[Ping]:
        """根据 ID 获取 Ping"""
        pass
    
    @abstractmethod
    async def create(self, ping: Ping) -> Ping:
        """创建 Ping"""
        pass
    
    @abstractmethod
    async def update(self, ping: Ping) -> Ping:
        """更新 Ping"""
        pass
    
    @abstractmethod
    async def delete(self, ping_id: str) -> None:
        """删除 Ping"""
        pass

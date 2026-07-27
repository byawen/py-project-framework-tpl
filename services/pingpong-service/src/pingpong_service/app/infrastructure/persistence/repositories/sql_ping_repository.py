"""SQL Ping 仓储实现模块

Ping 仓储接口的 SQL 实现
"""
from typing import Optional
from sqlalchemy import select
from injector import inject

from services_common.database import DatabaseManager
from pingpong_service.foundation.logging import get_logger
from pingpong_service.app.domain.entities.ping import Ping
from pingpong_service.app.domain.repositories.ping_repository import PingRepository
from pingpong_service.app.infrastructure.persistence.models.ping_model import PingModel

logger = get_logger(__name__)


class SQLPingRepository(PingRepository):
    """PingRepository 的 SQL 实现"""
    
    @inject
    def __init__(self, dm: DatabaseManager):
        self.dm = dm
    
    def _to_entity(self, model: PingModel) -> Ping:
        """将 SQLAlchemy 模型转换为领域实体"""
        return Ping(
            ping_id=model.ping_id,
            message=model.message,
            created_at=model.created_at,
        )
    
    def _to_model(self, entity: Ping) -> PingModel:
        """将领域实体转换为 SQLAlchemy 模型"""
        return PingModel(
            ping_id=entity.ping_id,
            message=entity.message,
            created_at=entity.created_at,
        )
    
    async def get_by_id(self, ping_id: str) -> Optional[Ping]:
        """根据 ID 获取 Ping"""
        logger.info("按 ID 查询 Ping", operation="pingpong.repo.ping.get_by_id", ping_id=ping_id)
        async with self.dm.session() as session:
            result = await session.execute(
                select(PingModel).where(PingModel.ping_id == ping_id)
            )
            model = result.scalar_one_or_none()
        logger.info(
            "按 ID 查询 Ping 完成",
            operation="pingpong.repo.ping.get_by_id.success",
            ping_id=ping_id,
            found=model is not None,
        )
        return self._to_entity(model) if model else None
    
    async def create(self, ping: Ping) -> Ping:
        """创建 Ping"""
        async with self.dm.session() as session:
            model = self._to_model(ping)
            session.add(model)
            await session.flush()
        return ping
    
    async def update(self, ping: Ping) -> Ping:
        """更新 Ping"""
        async with self.dm.session() as session:
            result = await session.execute(
                select(PingModel).where(PingModel.ping_id == ping.ping_id)
            )
            model = result.scalar_one()
            model.message = ping.message
            model.created_at = ping.created_at
            await session.flush()
        return ping
    
    async def delete(self, ping_id: str) -> None:
        """删除 Ping"""
        async with self.dm.session() as session:
            result = await session.execute(
                select(PingModel).where(PingModel.ping_id == ping_id)
            )
            model = result.scalar_one()
            await session.delete(model)
            await session.flush()

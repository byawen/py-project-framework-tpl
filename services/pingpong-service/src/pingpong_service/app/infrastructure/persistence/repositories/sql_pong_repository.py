"""SQL Pong 仓储实现模块

Pong 仓储接口的 SQL 实现
"""
from typing import Optional
from sqlalchemy import select
from injector import inject

from services_common.database import DatabaseManager
from pingpong_service.foundation.logging import get_logger
from pingpong_service.app.domain.entities.ping import Pong
from pingpong_service.app.domain.repositories.pong_repository import PongRepository
from pingpong_service.app.infrastructure.persistence.models.pong_model import PongModel

logger = get_logger(__name__)


class SQLPongRepository(PongRepository):
    """PongRepository 的 SQL 实现"""
    
    @inject
    def __init__(self, dm: DatabaseManager):
        self.dm = dm
    
    def _to_entity(self, model: PongModel) -> Pong:
        """将 SQLAlchemy 模型转换为领域实体"""
        return Pong(
            pong_id=model.pong_id,
            data=model.data,
            created_at=model.created_at,
        )
    
    def _to_model(self, entity: Pong) -> PongModel:
        """将领域实体转换为 SQLAlchemy 模型"""
        return PongModel(
            pong_id=entity.pong_id,
            data=entity.data,
            created_at=entity.created_at,
        )
    
    async def get_by_id(self, pong_id: str) -> Optional[Pong]:
        """根据 ID 获取 Pong"""
        logger.info("按 ID 查询 Pong", operation="pingpong.repo.pong.get_by_id", pong_id=pong_id)
        async with self.dm.session() as session:
            result = await session.execute(
                select(PongModel).where(PongModel.pong_id == pong_id)
            )
            model = result.scalar_one_or_none()
        logger.info(
            "按 ID 查询 Pong 完成",
            operation="pingpong.repo.pong.get_by_id.success",
            pong_id=pong_id,
            found=model is not None,
        )
        return self._to_entity(model) if model else None
    
    async def create(self, pong: Pong) -> Pong:
        """创建 Pong"""
        async with self.dm.session() as session:
            model = self._to_model(pong)
            session.add(model)
            await session.flush()
        return pong
    
    async def update(self, pong: Pong) -> Pong:
        """更新 Pong"""
        async with self.dm.session() as session:
            result = await session.execute(
                select(PongModel).where(PongModel.pong_id == pong.pong_id)
            )
            model = result.scalar_one()
            model.data = pong.data
            model.created_at = pong.created_at
            await session.flush()
        return pong
    
    async def delete(self, pong_id: str) -> None:
        """删除 Pong"""
        async with self.dm.session() as session:
            result = await session.execute(
                select(PongModel).where(PongModel.pong_id == pong_id)
            )
            model = result.scalar_one()
            await session.delete(model)
            await session.flush()

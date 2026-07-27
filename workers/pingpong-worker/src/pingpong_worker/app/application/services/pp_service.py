"""PingAndPong 服务层

提供业务逻辑封装，支持事务管理和跨仓储操作。
"""

from typing import Optional
from injector import inject
from workers_common.database import DatabaseManager

from pingpong_worker.app.domain.entities.ping import Ping, Pong
from pingpong_worker.app.domain.repositories.ping_repository import PingRepository
from pingpong_worker.app.domain.repositories.pong_repository import PongRepository
from pingpong_worker.app.domain.value_objects.ping_message import PingMessage
from pingpong_worker.app.domain.value_objects.pong_data import PongData


class PPService:
    """PingAndPong 服务 - 封装业务逻辑

    使用示例:

        # 简单操作
        ping = await ping_pong_service.get_ping(ping_id)

        # 事务操作
        async with ping_pong_service.transaction() as session:
            await ping_pong_service.create_ping(ping)
            await ping_pong_service.create_pong(pong)
    """

    @inject
    def __init__(
        self,
        dm: DatabaseManager,
        ping_repo: PingRepository,
        pong_repo: PongRepository,
    ):
        self.dm = dm
        self.ping_repo = ping_repo
        self.pong_repo = pong_repo

    async def transaction(self):
        """获取事务上下文管理器

        Returns:
            AsyncSession: 事务会话
        """
        return self.dm.transaction()

    # ============ Ping 操作 ============

    async def get_ping(self, ping_id: str) -> Optional[Ping]:
        """根据 ID 获取 Ping"""
        return await self.ping_repo.get_by_id(ping_id)

    async def create_ping(self, message: str) -> Ping:
        """创建 Ping"""
        ping_message = PingMessage(message)
        ping = Ping(message=ping_message)
        return await self.ping_repo.create(ping)

    async def update_ping(self, ping_id: str, message: str) -> Optional[Ping]:
        """更新 Ping"""
        ping = await self.ping_repo.get_by_id(ping_id)
        if ping:
            ping.message = PingMessage(message)
            return await self.ping_repo.update(ping)
        return None

    async def delete_ping(self, ping_id: str) -> None:
        """删除 Ping"""
        await self.ping_repo.delete(ping_id)

    # ============ Pong 操作 ============

    async def get_pong(self, pong_id: str) -> Optional[Pong]:
        """根据 ID 获取 Pong"""
        return await self.pong_repo.get_by_id(pong_id)

    async def create_pong(self, data: str) -> Pong:
        """创建 Pong"""
        pong_data = PongData(data)
        pong = Pong(data=pong_data)
        return await self.pong_repo.create(pong)

    async def update_pong(self, pong_id: str, data: str) -> Optional[Pong]:
        """更新 Pong"""
        pong = await self.pong_repo.get_by_id(pong_id)
        if pong:
            pong.data = PongData(data)
            return await self.pong_repo.update(pong)
        return None

    async def delete_pong(self, pong_id: str) -> None:
        """删除 Pong"""
        await self.pong_repo.delete(pong_id)

    # ============ 组合操作 ============

    async def ping_and_pong(self, message: str, data: str) -> tuple[Ping, Pong]:
        """在一个事务中创建 Ping 和 Pong

        使用示例:
            ping, pong = await service.ping_and_pong("hello", "world")
        """
        async with self.dm.transaction() as session:
            ping = await self.create_ping(message)
            pong = await self.create_pong(data)
            return ping, pong

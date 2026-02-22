"""Ping 查询模块

获取 Ping 查询
"""
from typing import Optional
from dataclasses import dataclass
import uuid
from injector import inject

from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from pingpong_service.clients.github.oauth import GithubOauthAPIClient
from pingpong_service.app.domain.entities.ping import Ping
from pingpong_service.app.domain.repositories.ping_repository import PingRepository
from pingpong_service.clients.other_service.api_proxy import OtherServiceAPIProxy
from pingpong_service.foundation.logging import LogManager
from services_common.logging import Logger


@dataclass
class PingQueryResult:
    """Ping 查询结果"""
    message: str
    ping: Optional[Ping] = None


class PingQuery:
    """Ping 查询处理器"""
    
    @inject
    def __init__(
        self,
        db: AsyncSession,
        redis: Redis,
        ping_repo: PingRepository,
        log_manager: LogManager,
        github_client: GithubOauthAPIClient,
        other_service: OtherServiceAPIProxy,
    ):
        self.db = db
        self.redis = redis
        self.ping_repo = ping_repo
        self.logger: Logger = log_manager.get_logger(__name__)
        self.github_client = github_client
        self.other_service = other_service

    async def execute(self) -> PingQueryResult:
        """执行 Ping 查询 - 返回 'ping, xxxxxx'"""
        self.logger.debug("Executing Ping query")
        
        # 生成一个唯一的 ID
        ping_id = str(uuid.uuid4())

        # 请求外部服务：如github
        result = await self.github_client.oauth_request()

        # 请求外部服务：other service
        result2 = await self.other_service.get_user_by_id("awen")
        
        # 创建 Ping 实体
        ping = Ping(
            id=ping_id,
            message="ping, " + str(result) + " - " + str(result2),
        )
        
        # 从数据库中获取
        # await self.ping_repo.get_by_id(ping)
        
        return PingQueryResult(
            message=str(ping),
            ping=ping,
        )

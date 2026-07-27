from abc import ABC, abstractmethod
from typing import Optional

from pingpong_worker.app.domain import Ping


class PPCache(ABC):
    """PingPong 缓存接口"""

    @abstractmethod
    async def get_ping_cache(self, pong_id: str) -> Optional[Ping]:
        """获取 Ping 缓存"""
        pass

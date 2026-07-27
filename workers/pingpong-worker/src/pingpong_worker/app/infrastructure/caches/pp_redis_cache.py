"""Redis 缓存工具模块

Redis 缓存工具
"""

from injector import inject

from pingpong_worker.foundation.config import Settings
from workers_common.redis import RedisManager


class PPRedisCache:
    """Redis 缓存处理器"""

    @inject
    def __init__(self, rm: RedisManager, setting: Settings):
        self.prefix = setting.REDIS_PREFIX or "pipo"
        self.rm = rm

    def _make_key(self, key: str) -> str:
        """生成带前缀的 key"""
        return f"{self.prefix}:{key}"

    async def get_ping_cache(self) -> str:
        return "hello"

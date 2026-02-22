"""
Redis 客户端工具模块 - 所有服务共享的 Redis 客户端

使用示例:

    _redis_manager = RedisManager(
            redis_url=redis_url or settings.REDIS_URL,
            max_connections=max_connections,
            decode_responses=decode_responses,
        )
        
    # 健康检查
    is_healthy = await redis_manager.health_check()
"""

from typing import Optional, Any
import json
from redis.asyncio import Redis, ConnectionPool
from redis.asyncio.client import Pipeline
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    RetryError,
)


class RedisManager:
    """Redis 连接管理器 - 支持重试和健康检查"""
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        max_connections: int = 50,
        decode_responses: bool = True,
        # 重试配置
        retry_enabled: bool = True,
        retry_max_attempts: int = 3,
        retry_min_wait: float = 1.0,
        retry_max_wait: float = 10.0,
    ):
        self.redis_url = redis_url
        self.max_connections = max_connections
        self.decode_responses = decode_responses

        # 重试配置
        self.retry_enabled = retry_enabled
        self.retry_max_attempts = retry_max_attempts
        self.retry_min_wait = retry_min_wait
        self.retry_max_wait = retry_max_wait
        
        self._pool: Optional[ConnectionPool] = None
        self._client: Optional[Redis] = None
    
    @property
    def pool(self) -> ConnectionPool:
        """获取或创建连接池"""
        if self._pool is None:
            self._pool = ConnectionPool.from_url(
                self.redis_url,
                max_connections=self.max_connections,
                decode_responses=self.decode_responses,
            )
        return self._pool
    
    @property
    def client(self) -> Redis:
        """获取 Redis 客户端"""
        if self._client is None:
            self._client = Redis(connection_pool=self.pool)
        return self._client
    
    def _create_retry_decorator(self):
        """创建重试装饰器"""
        return retry(
            stop=stop_after_attempt(self.retry_max_attempts),
            wait=wait_exponential(
                multiplier=1,
                min=self.retry_min_wait,
                max=self.retry_max_wait
            ),
            reraise=True,
        )

    async def execute_with_retry(self, func, *args, **kwargs):
        """带重试机制执行异步函数"""
        if not self.retry_enabled:
            return await func(*args, **kwargs)

        retry_decorator = self._create_retry_decorator()
        wrapped_func = retry_decorator(func)

        try:
            return await wrapped_func(*args, **kwargs)
        except RetryError as e:
            raise e.last_attempt.exception from e.last_attempt.exception

    async def health_check(self) -> bool:
        """健康检查 - 检查 Redis 连接是否正常

        Returns:
            bool: 连接正常返回 True，否则返回 False
        """
        try:
            return await self.client.ping()
        except Exception:
            return False

    async def get(self, key: str) -> Optional[str]:
        """根据 key 获取值"""
        return await self.client.get(key)
    
    async def set(
        self,
        key: str,
        value: Any,
        ex: Optional[int] = None,
        px: Optional[int] = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        """设置键值对"""
        if not isinstance(value, str):
            value = json.dumps(value)
        return await self.client.set(key, value, ex=ex, px=px, nx=nx, xx=xx)
    
    async def delete(self, *keys: str) -> int:
        """删除 keys"""
        return await self.client.delete(*keys)
    
    async def exists(self, key: str) -> bool:
        """检查 key 是否存在"""
        return await self.client.exists(key) > 0
    
    async def expire(self, key: str, seconds: int) -> bool:
        """设置过期时间"""
        return await self.client.expire(key, seconds)
    
    async def increment(self, key: str, amount: int = 1) -> int:
        """递增数值"""
        return await self.client.incr(key, amount)
    
    async def decrement(self, key: str, amount: int = 1) -> int:
        """递减数值"""
        return await self.client.decr(key, amount)
    
    async def ttl(self, key: str) -> int:
        """获取生存时间"""
        return await self.client.ttl(key)

    async def hset(self, name: str, key: str = None, value: Any = None, mapping: dict = None) -> int:
        """设置哈希字段"""
        if mapping:
            return await self.client.hset(name, mapping=mapping)
        if not isinstance(value, str):
            value = json.dumps(value)
        return await self.client.hset(name, key, value)
    
    async def hget(self, name: str, key: str) -> Optional[str]:
        """获取哈希字段"""
        return await self.client.hget(name, key)
    
    async def hgetall(self, name: str) -> dict:
        """获取所有哈希字段"""
        return await self.client.hgetall(name)
    
    async def hdel(self, name: str, *keys: str) -> int:
        """删除哈希字段"""
        return await self.client.hdel(name, *keys)
    
    async def pipeline(self) -> Pipeline:
        """创建管道"""
        return await self.client.pipeline()
    
    async def close(self) -> None:
        """关闭 Redis 连接"""
        if self._client:
            await self._client.aclose()
            self._client = None
        if self._pool:
            await self._pool.disconnect()
            self._pool = None

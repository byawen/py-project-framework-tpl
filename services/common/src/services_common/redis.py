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

from typing import Optional, Any, Awaitable, Callable
import asyncio
import inspect
import json
import os
import socket
import uuid
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
        socket_timeout: float | None = 10.0,
        socket_connect_timeout: float | None = 5.0,
        health_check_interval: int = 30,
        retry_on_timeout: bool = True,
        # 重试配置
        retry_enabled: bool = True,
        retry_max_attempts: int = 3,
        retry_min_wait: float = 1.0,
        retry_max_wait: float = 10.0,
    ):
        self.redis_url = redis_url
        self.max_connections = max_connections
        self.decode_responses = decode_responses
        self.socket_timeout = socket_timeout
        self.socket_connect_timeout = socket_connect_timeout
        self.health_check_interval = health_check_interval
        self.retry_on_timeout = retry_on_timeout

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
                socket_timeout=self.socket_timeout,
                socket_connect_timeout=self.socket_connect_timeout,
                health_check_interval=self.health_check_interval,
                retry_on_timeout=self.retry_on_timeout,
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


class RedisWorkerLock:
    """基于 Redis 的单活后台 Worker 锁。"""

    _RELEASE_SCRIPT = """
    if redis.call("GET", KEYS[1]) == ARGV[1] then
        return redis.call("DEL", KEYS[1])
    end
    return 0
    """

    _RENEW_SCRIPT = """
    if redis.call("GET", KEYS[1]) == ARGV[1] then
        return redis.call("EXPIRE", KEYS[1], ARGV[2])
    end
    return 0
    """

    def __init__(
        self,
        redis: RedisManager,
        lock_key: str,
        ttl_seconds: int = 30,
        renew_seconds: int = 10,
        owner_id: str | None = None,
    ) -> None:
        self._redis = redis
        self.lock_key = lock_key
        self.ttl_seconds = ttl_seconds
        self.renew_seconds = renew_seconds
        self.owner_id = owner_id or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex}"
        self._renew_task: asyncio.Task | None = None
        self._running = False

    async def acquire(self) -> bool:
        acquired = await self._redis.client.set(
            self.lock_key,
            self.owner_id,
            ex=self.ttl_seconds,
            nx=True,
        )
        return bool(acquired)

    async def release(self) -> bool:
        released = await self._redis.client.eval(
            self._RELEASE_SCRIPT,
            1,
            self.lock_key,
            self.owner_id,
        )
        return bool(released)

    async def renew(self) -> bool:
        renewed = await self._redis.client.eval(
            self._RENEW_SCRIPT,
            1,
            self.lock_key,
            self.owner_id,
            self.ttl_seconds,
        )
        return bool(renewed)

    def start_auto_renew(
        self,
        on_lost: Callable[[], Any] | Callable[[], Awaitable[Any]] | None = None,
    ) -> None:
        if self._renew_task and not self._renew_task.done():
            return
        self._running = True
        self._renew_task = asyncio.create_task(self._renew_loop(on_lost))

    async def stop_auto_renew(self) -> None:
        self._running = False
        if self._renew_task:
            self._renew_task.cancel()
            try:
                await self._renew_task
            except asyncio.CancelledError:
                pass
            self._renew_task = None

    async def _renew_loop(
        self,
        on_lost: Callable[[], Any] | Callable[[], Awaitable[Any]] | None,
    ) -> None:
        while self._running:
            await asyncio.sleep(self.renew_seconds)
            try:
                if await self.renew():
                    continue
            except asyncio.CancelledError:
                raise
            except Exception:
                pass

            self._running = False
            if on_lost:
                result = on_lost()
                if inspect.isawaitable(result):
                    await result
            break

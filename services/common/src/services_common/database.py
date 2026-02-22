"""
Databases 客户端工具

使用示例:

    _default_db_manager = DatabaseManager(
                database_url=database_url or settings.DATABASE_URL,
                pool_size=pool_size,
                max_overflow=max_overflow,
                echo=echo,
            )
            
    # 事务使用
    async with dm.transaction() as session:
        await ping_repo.create(ping)
        await pong_repo.create(pong)
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import AsyncAdaptedQueuePool
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    RetryError,
)


class BaseModel(DeclarativeBase):
    """SQLAlchemy 共享基类

    所有服务的 ORM 模型都应该继承这个 Base 类
    """
    pass


class DatabaseManager:
    """数据库连接管理器 - 支持事务和重试"""

    def __init__(
        self,
        database_url: str,
        pool_size: int = 20,
        max_overflow: int = 10,
        echo: bool = False,
        # 重试配置
        retry_enabled: bool = True,
        retry_max_attempts: int = 3,
        retry_min_wait: float = 1.0,
        retry_max_wait: float = 10.0,
    ):
        self.database_url = database_url
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.echo = echo

        # 重试配置
        self.retry_enabled = retry_enabled
        self.retry_max_attempts = retry_max_attempts
        self.retry_min_wait = retry_min_wait
        self.retry_max_wait = retry_max_wait

        self._engine: Optional[AsyncEngine] = None
        self._session_maker: Optional[async_sessionmaker[AsyncSession]] = None

    @property
    def engine(self) -> AsyncEngine:
        """获取或创建异步引擎"""
        if self._engine is None:
            self._engine = create_async_engine(
                self.database_url,
                poolclass=AsyncAdaptedQueuePool,
                pool_size=self.pool_size,
                max_overflow=self.max_overflow,
                echo=self.echo,
                pool_pre_ping=True,
                pool_recycle=3600,
            )
        return self._engine

    @property
    def session_maker(self) -> async_sessionmaker[AsyncSession]:
        """获取或创建会话工厂"""
        if self._session_maker is None:
            self._session_maker = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False,
            )
        return self._session_maker

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[AsyncSession, None]:
        """事务上下文管理器 - 用于跨多个仓储的操作

        使用示例:
            async with db_manager.transaction() as session:
                await ping_repo.create(ping)
                await pong_repo.create(pong)
                # 自动提交，如果出错自动回滚
        """
        async with self.session_maker() as session:
            async with session.begin():
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """会话上下文管理器 - 简化仓储实现

        使用示例:
            async with db_manager.session() as session:
                result = await session.execute(...)
        """
        async with self.session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

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
        """带重试机制执行异步函数

        使用示例:
            result = await db_manager.execute_with_retry(
                some_async_function, arg1, arg2
            )
        """
        if not self.retry_enabled:
            return await func(*args, **kwargs)

        retry_decorator = self._create_retry_decorator()
        wrapped_func = retry_decorator(func)

        try:
            return await wrapped_func(*args, **kwargs)
        except RetryError as e:
            raise e.last_attempt.exception from e.last_attempt.exception

    async def create_all(self) -> None:
        """创建所有表"""
        async with self.engine.begin() as conn:
            await conn.run_sync(BaseModel.metadata.create_all)

    async def drop_all(self) -> None:
        """删除所有表"""
        async with self.engine.begin() as conn:
            await conn.run_sync(BaseModel.metadata.drop_all)

    async def close(self) -> None:
        """关闭数据库连接"""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_maker = None


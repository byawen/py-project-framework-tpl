"""Alembic Environment Configuration

Alembic 环境配置 - 支持异步 SQLAlchemy
"""
import asyncio
import os
from logging.config import fileConfig

# 加载 .env 文件
from dotenv import load_dotenv

# 显式指定 .env 文件路径（alembic.ini 同目录）
env_file = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(env_file)

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.orm import declarative_base

from alembic import context

# ============================================================
# 创建服务独立的 Base 类（用于 alembic 迁移）
# 这样每个服务的迁移只会扫描自己的模型
# ============================================================
Base = declarative_base()

# Import all models here and bind to service-specific Base
from pingpong_service.app.infrastructure.persistence.models.ping_model import PingModel
from pingpong_service.app.infrastructure.persistence.models.pong_model import PongModel

# 将模型表复制到服务独立的 Base（关键步骤！）
for model in [PingModel, PongModel]:
    model.__table__.metadata = Base.metadata
    Base.metadata._add_table(model.__table__.name, model.__table__.schema)

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# 设置数据库 URL（从环境变量读取）
database_url = os.getenv(
    "DATABASE_URL", 
    "postgresql+asyncpg://postgres:postgres@localhost:5432/pingpong-db"
)
config.set_main_option("sqlalchemy.url", database_url)

# 读取 version_table 配置（从 alembic.ini 或环境变量）
version_table = os.getenv("ALEMBIC_VERSION_TABLE", "pipo_alembic_version")
config.set_main_option("version_table", version_table)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    # 显式传递 version_table 参数
    context.configure(
        connection=connection, 
        target_metadata=target_metadata,
        version_table=config.get_main_option("version_table"),
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = config.get_main_option("sqlalchemy.url")
    
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

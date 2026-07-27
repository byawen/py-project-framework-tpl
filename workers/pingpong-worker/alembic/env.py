"""Alembic Environment Configuration

Alembic 环境配置 - 支持异步 SQLAlchemy
"""
import asyncio
import os
from logging.config import fileConfig

# 加载 .env 文件
from dotenv import load_dotenv
from workers_common import BaseModel

# 显式指定 .env 文件路径（alembic.ini 同目录）
env_file = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(env_file)

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.orm import declarative_base

from alembic import context

# ============================================================
# 只处理本服务的表，忽略其他服务的表（防止 autogenerate 删除其他服务的表）
# ============================================================
SERVICE_TABLE_PREFIXES = "pipo_"


def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table":
        return name.startswith(SERVICE_TABLE_PREFIXES)
    return True


# Import all models here and bind to service-specific Base
import pingpong_worker.app.infrastructure.persistence.models

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
target_metadata = BaseModel.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    # 显式传递 version_table 参数
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table=config.get_main_option("version_table"),
        include_object=include_object,
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
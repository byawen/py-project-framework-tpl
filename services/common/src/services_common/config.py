"""配置管理模块 - 所有服务共享的配置"""

from functools import lru_cache
from typing import Optional, Any
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """应用基础配置 - 所有服务共享的配置项"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 应用设置
    APP_NAME: str = "app-service"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"  # production/development

    # 日志设置
    LOG_LEVEL: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    LOG_DIR: str = "./logs"  # 日志目录
    LOG_CONSOLE: bool = True  # 是否输出到控制台
    LOG_FILE: bool = False    # 是否写入文件（需同时配置 LOG_DIR）
    LOG_FILE_MAX_BYTES: int = 100 * 1024 * 1024  # 单个日志文件最大大小，默认 100MB
    LOG_FILE_BACKUP_COUNT: int = 100             # 最多保留的滚动备份文件数量

    # 服务器设置
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # 跨域资源共享
    CORS_ORIGINS: list[str] = ["*"]

    # 模式
    MODEL: str = "standalone"    # all-in-one or standalone

    # 本服务对外暴露的 base URL
    SERVICE_BASE_URL: str = "http://localhost:8000"


class DatabaseSettings(BaseSettings):
    """数据库配置"""
    
    # 主数据库
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/demo_main"
    )
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_ECHO: bool = False


class RedisSettings(BaseSettings):
    """Redis 配置"""

    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 50
    REDIS_DECODE_RESPONSES: bool = True
    REDIS_SOCKET_TIMEOUT: float = 10.0
    REDIS_SOCKET_CONNECT_TIMEOUT: float = 5.0
    REDIS_HEALTH_CHECK_INTERVAL: int = 30
    REDIS_RETRY_ON_TIMEOUT: bool = True


class WorkersSettings(BaseSettings):
    """消息中间件配置 — 服务端任务派发（producer）

    统一容纳所有中间件类型的配置字段。当前只有 Celery 相关字段，
    后续可在此追加 Pubsub、RabbitMQ 等中间件的配置段。

    与 workers_common.config.WorkersSettings（consumer 端）共享同一套字段名，
    保证 services/common/task_publisher 和 workers/common/broker 配置对齐。
    service 只需派发不需要消费，故不含 worker_concurrency / prefetch_multiplier 等消费端字段。
    """

    # ── Celery 连接 ──
    CELERY_BROKER_URL: str = "redis://localhost:6379/4"
    CELERY_BROKER_RESULT_BACKEND: str = "redis://localhost:6379/5"

    # ── Celery 序列化 ──
    CELERY_TASK_SERIALIZER: str = "json"
    CELERY_RESULT_SERIALIZER: str = "json"
    CELERY_ACCEPT_CONTENT: str = "json"

    # ── Celery 时区 ──
    CELERY_TIMEZONE: str = "Asia/Shanghai"
    CELERY_ENABLE_UTC: bool = True

    # ── Celery 队列路由（service 可按需覆盖）──
    CELERY_TASK_ROUTES: dict = {}

    # ── 后续追加其他中间件配置示例 ──
    # PUBSUB_URL: str = ""
    # RABBITMQ_URL: str = ""


class LLMSettings(BaseSettings):
    """大语言模型提供商配置"""
    # Local/Private LLM
    LLM_BASE_URL: Optional[str] = None
    LLM_API_KEY: Optional[str] = None
    LLM_MODEL: Optional[str] = None


class VectorStoreSettings(BaseSettings):
    """向量数据库配置"""
    # Qdrant (optional)
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_API_KEY: Optional[str] = None


class SecuritySettings(BaseSettings):
    """安全配置"""

    # JWT 配置
    JWT_SECRET_KEY: str = "change-this-secret-key-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60  # 1小时
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 180 # 刷新3小时


class RateLimitSettings(BaseSettings):
    """限流配置"""

    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_PER_HOUR: int = 1000
    

class MetricsSettings(BaseSettings):
    """监控配置"""

    ENABLE_METRICS: bool = True
    METRICS_PORT: int = 9090


class Settings(
    AppSettings,
    DatabaseSettings,
    RedisSettings,
    WorkersSettings,
    LLMSettings,
    VectorStoreSettings,
    SecuritySettings,
    RateLimitSettings,
    MetricsSettings,
):
    """所有服务的综合配置 - 组合所有配置类"""

    pass


@lru_cache
def get_settings() -> Settings:
    """获取缓存的配置实例"""
    return Settings()

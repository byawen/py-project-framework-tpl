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

    # 服务器设置
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # 跨域资源共享
    CORS_ORIGINS: list[str] = ["*"]

    # 模式
    MODEL: str = "standalone"    # all-in-one or standalone


class DatabaseSettings(BaseSettings):
    """数据库配置"""
    
    # 主数据库
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/demo_main"
    )
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_ECHO: bool = False
    
    # 检查点数据库 (用于 LangGraph)
    CHECKPOINT_DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5433/demo_checkpoints"
    )
    CHECKPOINT_POOL_SIZE: int = 10
    CHECKPOINT_MAX_OVERFLOW: int = 20


class RedisSettings(BaseSettings):
    """Redis 配置"""
    
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 50
    REDIS_DECODE_RESPONSES: bool = True


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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 天


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

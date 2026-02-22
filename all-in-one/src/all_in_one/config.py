"""All-in-One Configuration - Unified settings for all services"""

from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 导入各服务配置类
from services_common.config import (
    AppSettings,
    DatabaseSettings,
    RedisSettings,
)


class Settings(AppSettings, DatabaseSettings, RedisSettings):
    """All-in-One mode settings - 继承公共配置 + 各服务配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ============================================
    # 公共配置 (继承自 AppSettings, DatabaseSettings, RedisSettings)
    # ============================================
    # APP_NAME, DEBUG, ENVIRONMENT, HOST, PORT, CORS_ORIGINS
    # DATABASE_URL, DB_POOL_SIZE, DB_MAX_OVERFLOW, DB_ECHO
    # REDIS_URL, REDIS_MAX_CONNECTIONS

    # ============================================
    # All-in-One 专用配置
    # ============================================
    APP_NAME: str = "all-in-one"

    # ============================================
    # 服务特定配置
    # ============================================

    # PingPong 服务配置
    def get_pingpong_settings(self):
        from pingpong_service.foundation.config import Settings as PingPongSettings
        """获取 PingPong 服务配置"""
        # 从当前配置中提取 PingPong 相关的配置
        return PingPongSettings(
            APP_NAME=self.APP_NAME + "-pingpong",
            DEBUG=self.DEBUG,
            ENVIRONMENT=self.ENVIRONMENT,
            HOST=self.HOST,
            PORT=self.PORT,
            CORS_ORIGINS=self.CORS_ORIGINS,
            DATABASE_URL=self.DATABASE_URL,
            DB_POOL_SIZE=self.DB_POOL_SIZE,
            DB_MAX_OVERFLOW=self.DB_MAX_OVERFLOW,
            DB_ECHO=self.DB_ECHO,
            REDIS_URL=self.REDIS_URL,
            REDIS_MAX_CONNECTIONS=self.REDIS_MAX_CONNECTIONS,
            REDIS_PREFIX="pingpong",
            GITHUB_SERVICE_URL="http://localhost:8003",
        )

@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()

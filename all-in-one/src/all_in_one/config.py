"""All-in-One Configuration - Unified settings for all services"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

# 服务配置类
from services_common import AppSettings, DatabaseSettings, RedisSettings, WorkersSettings
from pingpong_service.foundation.config import Settings as PingPongSettings

class AllInOneSettings(AppSettings, DatabaseSettings, RedisSettings, WorkersSettings, BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )


class Settings(
    AllInOneSettings,
    PingPongSettings,
    # service 配置注册
):
    """All-in-One mode settings - 继承各服务配置（各服务已继承基础配置）"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
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
    MODEL: str = "all-in-one"
    ALL_IN_ONE_SHARE_DB: bool = True
    ALL_IN_ONE_SHARE_REDIS: bool = True

    # ── Service 选择性启动开关 ──
    # 格式：逗号分隔的 service 名称列表，如 "tool-service,content-ops-service"
    # 默认 "*" 表示启动所有注册的 services
    ENABLED_SERVICES: str = "*"

    # ============================================
    # 服务特定配置
    # ============================================

    # PingPong 服务配置
    def get_pingpong_settings(self):
        """获取 PingPong 服务配置"""
        config_dict = vars(self).copy()
        config_dict.update({
            "MODEL": "all-in-one",
            "APP_NAME": self.APP_NAME + "-pingpong",
            "REDIS_PREFIX": "pipo",
        })
        return PingPongSettings(**config_dict)

    # 新增 Service 在此添加:
    # def get_xxxx_settings(self):
    #     """获取 XXXX 服务配置"""
    #     config_dict = vars(self).copy()
    #     config_dict.update({
    #         "MODEL": "all-in-one",
    #         "APP_NAME": self.APP_NAME + "-xxxxx",
    #         "REDIS_PREFIX": "xxxx",
    #     })
    #     return XXXXXSettings(**config_dict)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()

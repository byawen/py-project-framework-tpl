"""PingPong 服务的配置管理模块"""
from functools import lru_cache
from pydantic_settings import SettingsConfigDict
from services_common.config import AppSettings, DatabaseSettings, RedisSettings


class Settings(AppSettings, DatabaseSettings, RedisSettings):
    """PingPong 服务配置 - 继承公共配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    # 覆盖默认端口
    PORT: int = 8001
    
    # 服务特定配置
    REDIS_PREFIX: str = "pipo"
    
    # 外部服务配置
    GITHUB_SERVICE_URL: str = "http://localhost:8003"
    #
    OTHER_SERVICE_URL: str = "http://localhost:8001"


@lru_cache
def get_settings() -> Settings:
    """获取缓存的配置实例"""
    return Settings()

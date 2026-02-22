"""PingPong 服务的配置管理模块"""
from functools import lru_cache

from services_common.config import AppSettings, DatabaseSettings, RedisSettings


class Settings(AppSettings, DatabaseSettings, RedisSettings):
    """PingPong 服务配置 - 继承公共配置"""

    # 覆盖默认端口
    PORT: int = 8001
    
    # 服务特定配置
    REDIS_PREFIX: str = "PingPong"
    
    # 外部服务配置
    GITHUB_SERVICE_URL: str = "http://localhost:8003"


@lru_cache
def get_settings() -> Settings:
    """获取缓存的配置实例"""
    return Settings()

"""PingPong 服务的配置管理模块"""
from functools import lru_cache
from pydantic_settings import SettingsConfigDict
from services_common.config import AppSettings, DatabaseSettings, RedisSettings, WorkersSettings


class Settings(AppSettings, DatabaseSettings, RedisSettings, WorkersSettings):
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

    # ── 任务派发（向 pingpong-worker 投递异步任务）──
    # 继承 WorkersSettings 提供 CELERY_BROKER_URL/CELERY_BROKER_RESULT_BACKEND/CELERY_* 公共默认值
    # 业务级路由用服务前缀字段，register TaskPublisherManager 时显式覆盖 CELERY_TASK_ROUTES
    PIPO_CELERY_ACCEPT_CONTENT: str = "json"
    PIPO_CELERY_TASK_ROUTES: dict = {
        "pingpong_worker.echo_task": {"queue": "pingpong_worker.echo.process"},
    }

    # ── echo 任务协议常量（与 pingpong-worker 逐字对齐）──
    # topic 两段 {pkg}.{task}；queue 三段 {pkg}.{domain}.{sub}
    # worker 侧同名 PIPO_ECHO_TASK_TOPIC 必须与本字段一致
    PIPO_ECHO_TASK_TOPIC: str = "pingpong_worker.echo_task"
    PIPO_ECHO_TASK_QUEUE: str = "pingpong_worker.echo.process"
    # publisher 名称 — 在 infrastructure/modules.py 中 register 时指定的名称
    PIPO_ECHO_BROKER_NAME: str = "celery"


@lru_cache
def get_settings() -> Settings:
    """获取缓存的配置实例"""
    return Settings()

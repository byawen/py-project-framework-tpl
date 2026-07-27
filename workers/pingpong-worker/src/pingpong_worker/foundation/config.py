"""PingPong Worker 配置管理模块"""

from functools import lru_cache

from pydantic_settings import SettingsConfigDict
from workers_common import AppSettings, DatabaseSettings, RedisSettings, WorkersSettings


class Settings(AppSettings, DatabaseSettings, RedisSettings, WorkersSettings):
    """PingPong Worker 配置 - 继承公共配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    # ── Broker 专有配置 ──
    # 继承 workers_common.WorkersSettings 的全部 CELERY_ 默认值
    # 队列路由用 worker 专有前缀，register 时显式覆盖 CELERY_* 字段
    PIPO_CELERY_TASK_DEFAULT_QUEUE: str = "pingpong.default.default"
    PIPO_CELERY_TASK_ROUTES: dict = {
        "pingpong_worker.default": {"queue": "pingpong.default.default"},
        "pingpong_worker.pingpong": {"queue": "pingpong.test.ping"},
        "pingpong_worker.beat_demo": {"queue": "pingpong.test.beat_demo"},
    }
    # CELERY_TASK_QUEUES 留空 — 启动时从 TASK_ROUTES 自动派生
    PIPO_CELERY_TASK_QUEUES: str = ""

    # 任务超时（比默认更短）
    CELERY_TASK_TIME_LIMIT: int = 300
    CELERY_TASK_SOFT_TIME_LIMIT: int = 270

    # ── Celery Beat 定时任务 ──
    # 任何 worker 只需设 CELERY_BEAT_ENABLE=True + 填充 CELERY_BEAT_SCHEDULE 即可。
    # schedule 支持纯数据描述（由 CeleryBroker 自动解析为 crontab/timedelta 对象）：
    #   {"crontab": {"minute": 0, "hour": 3}}  → 每天 03:00
    #   {"timedelta": {"seconds": 3600}}       → 每 1 小时
    #   86400                                   → 每 86400 秒（interval）
    PIPO_CELERY_BEAT_ENABLE: bool = True
    PIPO_CELERY_BEAT_SCHEDULE_FILENAME: str = "./temp/celerybeat-schedule-pipo"
    PIPO_CELERY_BEAT_SCHEDULE: dict = {
        "beat-demo-every-1min": {
            "task": "pingpong_worker.beat_demo",
            "schedule": {"timedelta": {"minutes": 1}},
        },
    }

    REDIS_PREFIX: str = "pipo"

    # 外部服务配置
    GITHUB_SERVICE_URL: str = "http://localhost:8003"
    OTHER_SERVICE_URL: str = "http://localhost:8001"


@lru_cache
def get_settings() -> Settings:
    """获取缓存的配置实例"""
    return Settings()
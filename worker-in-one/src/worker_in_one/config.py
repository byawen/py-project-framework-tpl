"""Worker-in-One Configuration - Unified settings for all workers"""

from functools import lru_cache
from pydantic_settings import SettingsConfigDict

from workers_common import AppSettings, DatabaseSettings, RedisSettings, WorkersSettings
from pingpong_worker.foundation.config import Settings as PingPongWorkerSettings


class WorkerInOneSettings(
    AppSettings,
    DatabaseSettings,
    RedisSettings,
    WorkersSettings,
):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )


class Settings(
    WorkerInOneSettings,
    PingPongWorkerSettings,
):
    """Worker-in-One mode settings - 继承各 worker 配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    # ============================================
    # 公共配置 (继承自 AppSettings, DatabaseSettings, RedisSettings, WorkersSettings)
    # ============================================
    # APP_NAME, DEBUG, ENVIRONMENT
    # DATABASE_URL, DB_POOL_SIZE, DB_MAX_OVERFLOW, DB_ECHO
    # REDIS_URL, REDIS_MAX_CONNECTIONS
    # CELERY_BROKER_URL, CELERY_BROKER_RESULT_BACKEND, CELERY_*

    # ============================================
    # Worker-in-One 专用配置
    # ============================================
    APP_NAME: str = "worker-in-one"
    MODEL: str = "worker-in-one"
    WORKER_IN_ONE_SHARE_DB: bool = True
    WORKER_IN_ONE_SHARE_REDIS: bool = True
    CELERY_QUEUE_CONCURRENCY: str = (
        '{"pingpong_worker.test.ping":2,'
        '"pingpong_worker.beat_demo":1}'
    )

    # ============================================
    # Worker 特定配置
    # ============================================

    # PingPong Worker 配置
    def get_pingpong_worker_settings(self):
        """获取 PingPong Worker 配置"""
        config_dict = vars(self).copy()
        config_dict.update({
            "MODEL": "worker-in-one",
            "APP_NAME": self.APP_NAME + "-pingpong",
            "REDIS_PREFIX": "pipo",
            "CELERY_BROKER_URL": self.CELERY_BROKER_URL,
            "CELERY_BROKER_RESULT_BACKEND": self.CELERY_BROKER_RESULT_BACKEND,
            "CELERY_TASK_DEFAULT_QUEUE": self.PIPO_CELERY_TASK_DEFAULT_QUEUE,
            "CELERY_TASK_ROUTES": self.PIPO_CELERY_TASK_ROUTES,
            "CELERY_TASK_QUEUES": self.PIPO_CELERY_TASK_QUEUES,
            "CELERY_BEAT_ENABLE": self.PIPO_CELERY_BEAT_ENABLE,
            "CELERY_BEAT_SCHEDULE": self.PIPO_CELERY_BEAT_SCHEDULE,
            "CELERY_BEAT_SCHEDULE_FILENAME": self.PIPO_CELERY_BEAT_SCHEDULE_FILENAME,
        })
        return PingPongWorkerSettings(**config_dict)

    # 新增 worker 在此添加:
    # def get_xxx_worker_settings(self):
    #     config_dict = vars(self).copy()
    #     config_dict.update({
    #         "MODEL": "worker-in-one",
    #         "APP_NAME": self.APP_NAME + "-xxx",
    #         "REDIS_PREFIX": "xxx",
    #     })
    #     return XxxWorkerSettings(**config_dict)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()

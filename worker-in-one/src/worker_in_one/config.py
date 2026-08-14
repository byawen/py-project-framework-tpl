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
    # 已改用 thread_resources 方式，后续需要再配置打开
    WORKER_IN_ONE_SHARE_DB: bool = False
    WORKER_IN_ONE_SHARE_REDIS: bool = False
    CELERY_QUEUE_CONCURRENCY: str = ''

    # ── per-queue 执行池类型覆盖（方案 D）──
    # JSON dict: {"queue_name": "threads" | "prefork" | "solo"}
    # 默认空 = 全部 prefork（等价现状，向后兼容），灰度靠 env 注入。
    # 配合 CELERY_USE_THREADS_POOL feature flag 使用。
    CELERY_QUEUE_POOL: str = ""
    # feature flag：false 时忽略 CELERY_QUEUE_POOL，全部回退 prefork（一键回滚）。
    CELERY_USE_THREADS_POOL: bool = True

    # 聚合部署下，新 Worker 与 content-ops-worker 均通过 all-in-one HTTP 入口访问服务。
    COPSW_DATA_COLLECTOR_SERVICE_URL: str = "http://localhost:8002"
    DCOLW_DATA_COLLECTOR_SERVICE_URL: str = "http://localhost:8002"
    DCOLW_ASSET_SERVICE_URL: str = "http://localhost:8002"

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

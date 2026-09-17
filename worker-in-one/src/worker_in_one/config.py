"""Worker-in-One Configuration - Unified settings for all workers"""

from functools import lru_cache
from pydantic_settings import SettingsConfigDict

from workers_common import AppSettings, DatabaseSettings, RedisSettings, WorkersSettings
from workers_common.config import DictFromEnv
from pingpong_worker.foundation.config import Settings as PingPongWorkerSettings

class WorkerInOneSettings(AppSettings, DatabaseSettings, RedisSettings, WorkersSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )


class Settings(
    WorkerInOneSettings,
    PingPongWorkerSettings,
    # worker配置注册
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
    CELERY_QUEUE_CONCURRENCY: DictFromEnv = {
        # "pingpong.test.ping": 4,
        # "pingpong.test.beat_demo": 4,
        # "pingpong_worker.echo.process": 4,
    }

    # ── per-queue 执行池类型覆盖（方案 D）──
    # dict: {"queue_name": "threads" | "prefork" | "solo"}
    CELERY_QUEUE_POOL: DictFromEnv = {
        # "pingpong.test.ping": "threads",
        # "pingpong.test.beat_demo": "threads",
        # "pingpong_worker.echo.process": "threads",
    }
    # feature flag：false 时忽略 CELERY_QUEUE_POOL，全部回退 prefork（一键回滚）。
    CELERY_USE_THREADS_POOL: bool = True

    # ── Prometheus 指标上报（供 common-gateway-service /worker-metrics 聚合读取）──
    METRICS_ENABLED: bool = True
    # 采集周期（秒）；per-instance key TTL 自动取 3× 周期。
    METRICS_INTERVAL_SECONDS: int = 30
    # per-app 指标隔离 tag。多 SAE 应用部署时每个应用设不同值（cops/vimu/dcol/...），
    METRICS_APP_TAG: str = "default"
    # 上报 backlog 的队列剔除规则。实际监听队列 = ENABLED_WORKERS 过滤后实际
    METRICS_QUEUE_EXCLUDE_PATTERNS: str = "*"

    # ── Beat 单飞开关（多实例部署用）──
    # 默认 True 保持单实例现状不变。SAE 多实例时只在一个实例设 True，
    # 锁仍保留作兜底，防滚动发布间隙双 Beat + 重启补投）。
    CELERY_BEAT_ENABLED: bool = True

    # ── Worker 选择性启动开关 ──
    # 支持通过环境变量控制启动哪些 worker
    # 格式：逗号分隔的 worker 名称列表，如 "pingpong-worker,xxxxx-worker"
    ENABLED_WORKERS: str = "*"

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
            # per-worker DB/Redis 池开关（显式声明，隔离聚合 MRO 广播值）
            "DB_ENABLED": True,
            "REDIS_ENABLED": True,
        })
        return PingPongWorkerSettings(**config_dict)

    # 新增 worker 在此添加:
    # def get_xxx_worker_settings(self):
    #     config_dict = vars(self).copy()
    #     config_dict.update({
    #         "MODEL": "worker-in-one",
    #         "APP_NAME": self.APP_NAME + "-xxx",
    #         "REDIS_PREFIX": "xxx",
    #         # 显式声明本 worker 的 DB/Redis 池开关，隔离聚合 MRO 广播值
    #         # （见"关键传播陷阱"）。DB-FREE worker 写 False，DB-HEAVY 写 True。
    #         "DB_ENABLED": False,
    #         "REDIS_ENABLED": True,
    #     })
    #     return XxxWorkerSettings(**config_dict)

@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()

"""配置管理模块 - 所有 worker 共享的配置

与 services_common.config 的差异：
  - 移除 Web 专用字段（HOST / PORT / CORS_ORIGINS / SERVICE_BASE_URL）
  - 保留 worker 运行所需的应用、日志、数据库、Redis 等配置
"""

from functools import lru_cache
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """应用基础配置 - 所有 worker 共享的配置项"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 应用设置
    APP_NAME: str = "app-worker"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"  # production/development

    # 日志设置
    LOG_LEVEL: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    LOG_DIR: str = "./logs"  # 日志目录
    LOG_CONSOLE: bool = True  # 是否输出到控制台
    LOG_FILE: bool = False    # 是否写入文件（需同时配置 LOG_DIR）
    LOG_FILE_MAX_BYTES: int = 100 * 1024 * 1024  # 单个日志文件最大大小，默认 100MB
    LOG_FILE_BACKUP_COUNT: int = 100             # 最多保留的滚动备份文件数量

    # 模式
    MODEL: str = "standalone"    # worker-in-one or standalone


class DatabaseSettings(BaseSettings):
    """数据库配置"""

    # 主数据库
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/demo_main"
    )
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_ECHO: bool = False


class RedisSettings(BaseSettings):
    """Redis 配置"""

    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 50
    REDIS_DECODE_RESPONSES: bool = True
    REDIS_SOCKET_TIMEOUT: float = 10.0
    REDIS_SOCKET_CONNECT_TIMEOUT: float = 5.0
    REDIS_HEALTH_CHECK_INTERVAL: int = 30
    REDIS_RETRY_ON_TIMEOUT: bool = True


class LLMSettings(BaseSettings):
    """大语言模型提供商配置"""
    # Local/Private LLM
    LLM_BASE_URL: Optional[str] = None
    LLM_API_KEY: Optional[str] = None
    LLM_MODEL: Optional[str] = None


class WorkersSettings(BaseSettings):
    """消息中间件配置 — 消费端（consumer）

    统一容纳所有中间件类型的配置字段。当前只有 Celery 相关字段，
    后续可在此追加 Pubsub、RabbitMQ 等中间件的配置段。

    与 services_common.config.WorkersSettings（producer 端）共享同一套字段名，
    保证 workers/common/broker 和 services/common/task_publisher 配置对齐。
    worker 需要消费，故含 worker_concurrency / prefetch_multiplier / 超时 / 重试等消费端字段。
    """

    # ── Celery 连接 ──
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_BROKER_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # ── Celery 序列化 ──
    CELERY_TASK_SERIALIZER: str = "json"
    CELERY_RESULT_SERIALIZER: str = "json"
    CELERY_ACCEPT_CONTENT: str = "json"

    # ── Celery 时区 ──
    CELERY_TIMEZONE: str = "Asia/Shanghai"
    CELERY_ENABLE_UTC: bool = True

    # ── Celery 队列路由 ──
    CELERY_TASK_ROUTES: dict = {}
    CELERY_TASK_DEFAULT_QUEUE: str = "default"
    CELERY_TASK_QUEUES: str = ""

    # ── Celery 并发 ──
    CELERY_WORKER_CONCURRENCY: int = 4
    CELERY_WORKER_LOGLEVEL: str = "info"
    CELERY_WORKER_PREFETCH_MULTIPLIER: int = 1

    # ── Celery per-queue 并发覆盖 ──
    # JSON dict: {"queue_name": concurrency_int}
    # 未列出的队列回退到 CELERY_WORKER_CONCURRENCY
    # worker-in-one 模式下每个队列启动独立 WorkController 消费线程
    CELERY_QUEUE_CONCURRENCY: str = ""

    # ── Celery 超时 ──
    CELERY_TASK_TIME_LIMIT: int = 600
    CELERY_TASK_SOFT_TIME_LIMIT: int = 540

    # ── Celery 重试 ──
    CELERY_TASK_MAX_RETRIES: int = 3
    CELERY_TASK_RETRY_DELAY: int = 30

    # ── Celery 可靠性 ──
    CELERY_TASK_ACKS_LATE: bool = True
    # worker 被 SIGKILL/OOM 杀死时，reject 消息使其重回队列而非标记失败（需 task_acks_late=true）
    CELERY_TASK_REJECT_ON_WORKER_LOST: bool = True

    # ── Celery worker 回收（防 OOM 累积）──
    # pool worker 子进程执行 N 个任务后自动回收 fork 新进程，防止内存泄漏累积（0=禁用）
    CELERY_WORKER_MAX_TASKS_PER_CHILD: int = 50
    # pool worker RSS 超过此值（KB）后，当前任务完成后回收（0=禁用）
    CELERY_WORKER_MAX_MEMORY_PER_CHILD: int = 2_000_000  # 2GB

    # ── Celery Beat 定时调度 ──
    # 任何 worker 只需在自有 settings 中覆盖这两个字段即可启用 Beat：
    #   CELERY_BEAT_ENABLE = True
    #   CELERY_BEAT_SCHEDULE = { "task-name": {"task": "...", "schedule": crontab(...)} }
    # CeleryBroker.start() 会自动注入 beat_schedule 并添加 --beat 启动参数。
    # 多节点幂等由 handler 内部分布式锁保证。
    CELERY_BEAT_ENABLE: bool = False
    CELERY_BEAT_SCHEDULE: dict = {}
    # Beat 持久化调度状态的文件路径（默认在当前工作目录生成 celerybeat-schedule）
    # 建议指向 logs/ 或 data/ 目录，避免污染项目根目录
    CELERY_BEAT_SCHEDULE_FILENAME: str = "./temp/celerybeat-schedule"

    # ── 后续追加其他中间件配置示例 ──
    # PUBSUB_URL: str = ""
    # RABBITMQ_URL: str = ""


class Settings(
    AppSettings,
    DatabaseSettings,
    RedisSettings,
    LLMSettings,
    WorkersSettings,
):
    """所有 worker 的综合配置 - 组合所有配置类"""

    pass


@lru_cache
def get_settings() -> Settings:
    """获取缓存的配置实例"""
    return Settings()
"""配置管理模块 - 所有 worker 共享的配置

与 services_common.config 的差异：
  - 移除 Web 专用字段（HOST / PORT / CORS_ORIGINS / SERVICE_BASE_URL）
  - 保留 worker 运行所需的应用、日志、数据库、Redis 等配置
"""

import json
from functools import lru_cache
from typing import Annotated, Any, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import NoDecode

# DictFromEnv：env 以 JSON 字符串形式注入（值形如 {"q": 1}）。
# NoDecode 让 pydantic-settings 跳过对 dict 字段的自动 json.loads，
# 原始字符串进 _decode_json_map 统一解析：空串/非法 JSON 容错为 {}，
# 避免部署误写空值导致启动崩溃。运行时仍是普通 dict。
DictFromEnv = Annotated[dict[str, Any], NoDecode]


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
    # PG statement 级超时（毫秒）：防止单条 SQL 锁等待/hang 无限阻塞 worker 线程。
    # 0 = 不设（保持原行为）；默认 300000(5min)，worker DB 操作多为单行/小批量，足够宽松。
    DB_STATEMENT_TIMEOUT_MS: int = 300000

    # per-worker DB 池开关。False 时该 worker 不创建 DB manager/pool（thread_resources
    # 入口抛 DBDisabledError fail-fast）。各 worker 可在自己 config.py 继承时覆盖为 False
    # 自声明 DB-FREE；env DB_ENABLED=true 可临时全局强制开池。默认 True 向后兼容。
    DB_ENABLED: bool = True


class RedisSettings(BaseSettings):
    """Redis 配置"""

    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 50
    REDIS_DECODE_RESPONSES: bool = True
    REDIS_SOCKET_TIMEOUT: float = 10.0
    REDIS_SOCKET_CONNECT_TIMEOUT: float = 5.0
    REDIS_HEALTH_CHECK_INTERVAL: int = 30
    REDIS_RETRY_ON_TIMEOUT: bool = True

    # per-worker Redis 池开关，机制同 DB_ENABLED。本期默认全开不动（Redis 连接非
    # 当前瓶颈；beat 锁等关池有风险）。字段留在此供后续按需启用。
    REDIS_ENABLED: bool = True


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
    CELERY_TASK_ROUTES: DictFromEnv = {}
    CELERY_TASK_DEFAULT_QUEUE: str = "default"
    CELERY_TASK_QUEUES: str = ""

    # ── Celery 并发 ──
    CELERY_WORKER_CONCURRENCY: int = 4
    CELERY_WORKER_LOGLEVEL: str = "info"
    CELERY_WORKER_PREFETCH_MULTIPLIER: int = 1

    # ── Celery broker visibility_timeout ──
    # Redis broker 消息可见性超时（秒），必须 > 最长 task time_limit。
    # 默认 3600s(1h)；若任务硬超时超过 1h 必须调大，
    # 否则任务还在跑就被 Redis 重投给另一个 worker，导致同一任务占多并发槽。
    CELERY_BROKER_VISIBILITY_TIMEOUT_S: int = 3600

    # ── Celery per-queue 并发覆盖 ──
    # dict: {"queue_name": concurrency_int}
    # 未列出的队列回退到 CELERY_WORKER_CONCURRENCY
    # worker-in-one 模式下每个队列启动独立 WorkController 消费线程
    # env 注入写 JSON 字符串（由 _decode_json_map 解析为 dict）；
    # 缺失走默认 {}（全走默认并发），显式写空串非法（启动报错）。
    CELERY_QUEUE_CONCURRENCY: DictFromEnv = {}

    # ── Celery per-queue 执行池类型覆盖 ──
    # dict: {"queue_name": "threads" | "prefork" | "solo"}
    # 未列出的队列回退到 prefork（默认，向后兼容）。
    # - threads: 线程池，省进程、IO bound 队列适用；配合 async_bridge 的
    #   thread-local loop + thread-local 连接池（见 *_PER_THREAD 配置）。
    # - prefork: 进程池（默认），CPU 密集队列适用，绕开 GIL 真并行。
    # feature flag CELERY_USE_THREADS_POOL=false 时本配置被忽略，全部回退 prefork。
    # env 注入时写 JSON 字符串（由 _decode_json_map 解析为 dict），
    # 空字符串/缺失视为 {}（全走 prefork）。
    CELERY_QUEUE_POOL: DictFromEnv = {}

    @field_validator(
        "CELERY_TASK_ROUTES",
        "CELERY_QUEUE_CONCURRENCY",
        "CELERY_QUEUE_POOL",
        "CELERY_BEAT_SCHEDULE",
        mode="before",
    )
    @classmethod
    def _decode_json_map(cls, v: Any) -> Any:
        """env 注入的 JSON 字符串解析为 dict；空串/解析失败容错为 {}。

        字段用 NoDecode 标注，pydantic-settings 不再自动 json.loads，
        原始字符串在此统一解析：空字符串或非法 JSON 一律兜底为 {}，
        避免部署时误写空值导致启动崩溃。缺失（未设 env）走 class 默认值 {}。
        """
        if isinstance(v, str):
            if not v.strip():
                return {}
            try:
                return json.loads(v)
            except (json.JSONDecodeError, ValueError, TypeError):
                return {}
        return v
        return v

    # ── threads 池：每工作线程连接池上限 ──
    # threads 队列进程内每个工作线程拥有独立 loop + 独立 DB/Redis manager，
    # 池绑本线程 loop。小常驻池 + 溢出用完即释放，兼顾复用与峰值收敛。
    # 高并发（>10）需前置 pgbouncer transaction pooling 收敛后端真实连接。
    DB_POOL_SIZE_PER_THREAD: int = 5
    DB_MAX_OVERFLOW_PER_THREAD: int = 10
    REDIS_MAX_CONNECTIONS_PER_THREAD: int = 8

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
    CELERY_BEAT_SCHEDULE: DictFromEnv = {}
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
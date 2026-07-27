"""Worker-in-One 主入口

将所有 Worker 聚合在单一进程中运行，共享 DB/Redis 连接，
并通过聚合 Broker 抽象支持多种中间件（Celery / RabbitMQ / PubSub ...）。

启动流程:
1. 加载配置 → 初始化日志
2. asyncio.run(setup) → 共享资源 + 各 worker setup() + 收集 WorkerSpec
3. BrokerRunner.build(specs) → 按 broker_type 分组构建聚合 broker
4. BrokerRunner.run() → 并发运行所有 broker（主线程跑需要主线程的 broker，其余进后台线程）
"""

import asyncio
import signal
import sys
from typing import Callable

from worker_in_one.broker import BrokerRunner, WorkerSpec
from worker_in_one.foundation.config import Settings, get_settings
from worker_in_one.foundation.logging import get_logger
from worker_in_one.workers import workers_registry

from workers_common.logging import Logger, configure_logging, shutdown_file_logging


async def setup(_settings: Settings, logger: Logger) -> tuple[list[WorkerSpec], Callable]:
    """初始化所有 worker，返回 (worker_specs, cleaner)。"""
    return await workers_registry(_settings, logger)


def run_worker():
    """启动 Worker-in-One 入口。"""
    _settings = get_settings()

    # 初始化日志
    configure_logging(
        service_name=_settings.APP_NAME,
        log_dir=_settings.LOG_DIR,
        log_level=_settings.LOG_LEVEL,
        log_console=_settings.LOG_CONSOLE,
        log_file=_settings.LOG_FILE,
        log_file_max_bytes=_settings.LOG_FILE_MAX_BYTES,
        log_file_backup_count=_settings.LOG_FILE_BACKUP_COUNT,
    )

    logger = get_logger(__name__)
    logger.info(f"Starting Workers - Worker-in-One Mode with APP_NAME={_settings.APP_NAME}...")

    # 同步环境中运行异步 setup，收集各 worker 的 WorkerSpec
    specs, cleaner = asyncio.run(setup(_settings, logger))

    # 按 broker_type 分组构建聚合 broker
    runner = BrokerRunner(_settings, logger).build(specs)

    logger.info("All worker handlers registered, starting brokers...")

    # 优雅退出
    def _shutdown(signum, frame):
        logger.info("Received shutdown signal, stopping...")
        runner.stop()
        asyncio.run(cleaner())
        shutdown_file_logging()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # 并发运行所有聚合 broker（阻塞）
    runner.run()


if __name__ == "__main__":
    run_worker()
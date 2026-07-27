"""BrokerRunner - 聚合多 broker 的运行编排

职责:
  1. 接收 workers_registry() 产出的 WorkerSpec 列表
  2. 按 broker_type 分组，每组创建一个 AggregateBroker 实例
  3. 把同组 worker 的 handlers 注册进对应 broker
  4. 并发运行所有 broker：
     - requires_main_thread=True 的 broker（如 Celery）占用主线程（前台）
     - 其余 broker 在 daemon 线程后台运行
  5. 统一处理优雅退出

数据流:
    [WorkerSpec...] ──分组──> {broker_type: [spec...]}
                                   │
                          create_aggregate_broker(type)
                                   │
                          broker.register_worker(spec) × N
                                   │
                          后台线程组.start()  +  前台.start()
"""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from worker_in_one.broker.factory import create_aggregate_broker

if TYPE_CHECKING:
    from worker_in_one.broker.base import AggregateBroker
    from worker_in_one.broker.spec import WorkerSpec
    from worker_in_one.config import Settings
    from workers_common.logging import Logger


class BrokerRunner:
    """聚合 broker 运行器。"""

    def __init__(self, settings: "Settings", logger: "Logger") -> None:
        self._settings = settings
        self._logger = logger
        self._brokers: list["AggregateBroker"] = []

    def build(self, specs: list["WorkerSpec"]) -> "BrokerRunner":
        """按 broker_type 分组并构建各聚合 broker。"""
        grouped: dict[str, list["WorkerSpec"]] = {}
        for spec in specs:
            grouped.setdefault(spec.broker_type, []).append(spec)

        for broker_type, group in grouped.items():
            broker = create_aggregate_broker(broker_type, self._settings)
            for spec in group:
                broker.register_worker(spec)
            self._brokers.append(broker)
            self._logger.info(
                "Aggregate broker built",
                broker_type=broker_type,
                workers=[s.name for s in group],
            )

        if not self._brokers:
            self._logger.warning("No broker built: no worker registered")
        return self

    def run(self) -> None:
        """并发运行所有聚合 broker。

        约定: 同时至多一个 requires_main_thread 的 broker 占用主线程（前台阻塞）。
        其余 broker 在 daemon 线程运行。若没有任何前台 broker，则主线程 join 后台线程。
        """
        foreground: "AggregateBroker | None" = None
        background: list["AggregateBroker"] = []

        for broker in self._brokers:
            if broker.requires_main_thread and foreground is None:
                foreground = broker
            else:
                background.append(broker)

        threads: list[threading.Thread] = []
        for broker in background:
            t = threading.Thread(
                target=self._run_one,
                args=(broker,),
                name=f"broker-{broker.broker_type}",
                daemon=True,
            )
            t.start()
            threads.append(t)
            self._logger.info("Background broker started", broker_type=broker.broker_type)

        if foreground is not None:
            self._logger.info("Foreground broker starting", broker_type=foreground.broker_type)
            foreground.start()  # 阻塞直到收到停止信号
        else:
            # 没有前台 broker：主线程等待后台线程
            for t in threads:
                t.join()

    def _run_one(self, broker: "AggregateBroker") -> None:
        try:
            broker.start()
        except Exception as e:  # noqa: BLE001
            self._logger.error(
                "Broker crashed",
                broker_type=broker.broker_type,
                error=str(e),
            )

    def stop(self) -> None:
        """停止所有 broker。"""
        for broker in self._brokers:
            try:
                broker.stop()
            except Exception as e:  # noqa: BLE001
                self._logger.warning(
                    "Failed to stop broker",
                    broker_type=broker.broker_type,
                    error=str(e),
                )


__all__ = ["BrokerRunner"]
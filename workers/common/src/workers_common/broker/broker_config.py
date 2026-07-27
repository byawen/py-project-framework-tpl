"""Celery Broker 连接配置（消费端）

用于需要自定义连接参数（不同于 settings 默认值）的场景，
如一个 worker 同时消费多个不同地址的 celery broker。

与 services_common.task_publisher.CeleryBrokerConfig 对称，但独立定义
（workers/common 不依赖 services/common）。

典型用法：
    config = CeleryBrokerConfig(url="redis://other-host:6379/3", options={...})
    manager.register("celery-secondary", config)
"""

from typing import Any

from pydantic import BaseModel, Field


class CeleryBrokerConfig(BaseModel):
    """Celery broker 连接配置（消费端）

    Attributes:
        url: 连接地址
        result_backend: 结果回写地址（可选，celery 专用）
        options: 类型专属参数（如 celery 的 worker_concurrency / task_routes 等）
    """

    url: str = "redis://localhost:6379/1"
    result_backend: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


__all__ = ["CeleryBrokerConfig"]
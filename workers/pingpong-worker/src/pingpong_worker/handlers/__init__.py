"""Handlers 模块

消息/任务处理器，是 Worker 的入口交互层，等价于 Service 的 API 层。
"""

from pingpong_worker.handlers.registry import register_all_handlers

__all__ = ["register_all_handlers"]

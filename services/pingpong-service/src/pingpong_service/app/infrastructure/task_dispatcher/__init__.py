"""任务派发器包（向 worker 投递异步任务）

一任务一文件：每个派发器一个独立模块，在此包 __init__ 导出。
新增派发器：建 {task}_dispatcher.py + 在此 __init__ 导出 + 在 modules.py 注册。
"""
from pingpong_service.app.infrastructure.task_dispatcher.echo_dispatcher import EchoTaskDispatcher

__all__ = ["EchoTaskDispatcher"]

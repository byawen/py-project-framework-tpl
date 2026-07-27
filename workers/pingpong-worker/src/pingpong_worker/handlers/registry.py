"""Handler 注册表

集中注册所有消息处理器到 Broker。
新增 handler 只需:
1. 在 handlers/ 下创建处理器模块
2. 在此文件中 import 并 register_handler
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from workers_common.broker.base import BaseBroker


# Beat 定时任务 topic（Celery Beat 调度）
BEAT_DEMO_TOPIC = "pingpong_worker.beat_demo"


def register_all_handlers(broker: "BaseBroker") -> None:
    """注册所有消息处理器"""
    from pingpong_worker.handlers.pp_demo import handle_pingpong_task
    from pingpong_worker.handlers.beat_demo_handler import handle_beat_demo

    broker.register_handler("pingpong_worker.pingpong", handle_pingpong_task)
    broker.register_handler(BEAT_DEMO_TOPIC, handle_beat_demo)

    # 新增 handler 在此注册:
    # from pingpong_worker.handlers.your_handler import handle_your_task
    # broker.register_handler("pingpong_worker.tasks.your_task", handle_your_task)

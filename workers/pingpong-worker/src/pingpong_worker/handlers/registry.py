"""Handler 注册表

集中注册所有消息处理器到 Broker。
新增 handler 只需:
1. 在 handlers/ 下创建处理器模块
2. 在此文件中 import 并 register_handler
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from workers_common.broker.base import BaseBroker


def register_all_handlers(broker: "BaseBroker") -> None:
    """注册所有消息处理器"""
    from pingpong_worker.foundation.config import get_settings
    from pingpong_worker.handlers.pp_demo import handle_pingpong_task
    from pingpong_worker.handlers.beat_demo_handler import handle_beat_demo
    from pingpong_worker.handlers.echo_task_handler import handle_echo_task

    settings = get_settings()
    # topic 从配置读取（与 PIPO_CELERY_TASK_ROUTES / PIPO_CELERY_BEAT_SCHEDULE 逐字对齐）
    pingpong_topic = settings.PIPO_PINGPONG_TASK_TOPIC
    echo_task_topic = settings.PIPO_ECHO_TASK_TOPIC
    beat_demo_topic = settings.PIPO_BEAT_DEMO_TOPIC

    broker.register_handler(pingpong_topic, handle_pingpong_task)
    broker.register_handler(beat_demo_topic, handle_beat_demo)
    broker.register_handler(echo_task_topic, handle_echo_task)

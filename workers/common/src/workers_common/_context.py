"""请求/任务上下文变量 - 仅依赖标准库，零内部依赖。

logging.py 从此处导入 request_id 上下文变量以注入日志，
worker 场景下可由任务入口写入 request_id_context 以贯穿单次任务的日志链路。
"""
from contextvars import ContextVar

# 全局唯一的 request_id 上下文变量
request_id_context: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """获取当前上下文的 request_id。"""
    return request_id_context.get()
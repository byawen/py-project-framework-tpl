"""请求上下文变量 - 仅依赖标准库，零内部依赖。

注意：logging.py 内联了自己的 _request_id_ctx 用于读取 request_id。
此模块提供 request_id_context 供 middleware/request_id.py 写入，
两者共享同一个 ContextVar 实例需通过此模块统一管理。

logging.py 直接内联 ContextVar 定义，middleware 通过此模块的同名变量写入，
为了保持同一个实例，logging.py 的 _request_id_ctx 必须与此处的 request_id_context
是同一个对象。

最简方案：logging.py 从此处导入，但此处不导入任何 services_common 模块。
"""
from contextvars import ContextVar

# 全局唯一的 request_id 上下文变量
request_id_context: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """获取当前请求的 request_id。"""
    return request_id_context.get()

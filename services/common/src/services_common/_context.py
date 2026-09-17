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


# 全局唯一的 trace_id 上下文变量（跨服务链路追踪）
# 与 request_id 同样由 RequestIDMiddleware 写入；区别在于 trace_id 用于串联
# 一次完整业务链路（可能跨多个服务/请求），上游传了就透传，没传则生成新的。
trace_id_context: ContextVar[str] = ContextVar("trace_id", default="")


def get_trace_id() -> str:
    """获取当前请求的 trace_id（跨服务链路追踪标识）。"""
    return trace_id_context.get()


def get_context_headers() -> dict[str, str]:
    """收集跨服务调用需要透传的请求标识 headers。

    **只转发 ``X-Trace-ID``**（链路级标识），**不转发 ``X-Request-ID``**（请求级标识）。

    职责划分：
    - ``X-Request-ID``：请求级，标识**一次** HTTP 请求。每个服务独立生成 / 使用，
      **不跨服务透传**——下游服务由自己的中间件生成新的 request_id。用于幂等键 +
      单服务内日志关联。
    - ``X-Trace-ID``：链路级，标识**一次完整业务链路**（可能跨多服务多请求）。
      **必须跨服务透传**，保持整条链路连续。用于跨服务日志关联 + 排障。

    两者职责不重叠：request_id 管「单服务单请求」，trace_id 管「跨服务全链路」。
    若同时转发 request_id，下游会用上游的 request_id 做幂等键，导致语义混乱。

    用法::

        from services_common._context import get_context_headers
        headers = {**get_context_headers(), "Authorization": token}
        resp = await client.post(url, headers=headers, ...)
    """
    headers: dict[str, str] = {}
    tid = trace_id_context.get()
    if tid:
        headers["X-Trace-ID"] = tid
    return headers


# ── LLM usage_tokens 请求级累加器 ──
#
# LLMProvider 是 singleton（injector scope=None），历史上用 self.last_usage_tokens
# 累加每次调用的 token usage，再由调用方 pop_usage_tokens() 取出。singleton 上
# 的可变实例属性在并发请求间共享，会出现「请求 A pop 走请求 B 的 token」互窃。
# 改为按 contextvar 隔离：每个请求/任务上下文独立一份 list，互不干扰。
#
# 用 _UNSET sentinel 而非默认值 []，避免「所有未初始化上下文共享同一个 list 对象」。

_UNSET: object = object()
usage_tokens_context: ContextVar[object] = ContextVar("usage_tokens", default=_UNSET)


def get_usage_tokens_list() -> list[dict]:
    """获取当前上下文的 usage_tokens 累加 list，首次访问时惰性创建并绑定。"""
    val = usage_tokens_context.get()
    if val is _UNSET:
        val = []
        usage_tokens_context.set(val)
    return val  # type: ignore[return-value]


def reset_usage_tokens() -> None:
    """重置当前上下文的 usage_tokens（请求结束时清理）。"""
    usage_tokens_context.set(_UNSET)

"""httpx.AsyncClient 进程内连接池复用。

反模式：`async with httpx.AsyncClient() as client` 每次调用新建 TCP+TLS，
高并发 LLM 调用下握手开销显著、连接数失控。

本模块提供进程内共享的 AsyncClient（带 httpx.Limits 连接池上限）：
- 单一 client 跨所有外呼复用，httpx 内置连接池按 host 维度做 keep-alive
- 调用方传完整绝对 URL（httpx 会按 host 从连接池取复用连接）
- timeout 在每请求传入（httpx 支持 per-request timeout 覆盖），不固化在 client 上

适用：LLM provider、外部 SDK 等不可避免的外呼热路径。
"""
from __future__ import annotations

import httpx

# 进程内单例：所有外呼共用一个连接池客户端
_default_client: httpx.AsyncClient | None = None
# 每客户端连接上限
_DEFAULT_MAX_CONNECTIONS = 100
_DEFAULT_MAX_KEEPALIVE_CONNECTIONS = 20


def get_shared_async_client(
    *,
    max_connections: int = _DEFAULT_MAX_CONNECTIONS,
    max_keepalive_connections: int = _DEFAULT_MAX_KEEPALIVE_CONNECTIONS,
    follow_redirects: bool = False,
) -> httpx.AsyncClient:
    """获取进程内共享的 AsyncClient（带连接池上限，不绑定 base_url）。

    调用方传完整绝对 URL；httpx 按 host 从连接池取 keep-alive 连接。
    timeout 不在此传入——由调用方在每请求 client.post(..., timeout=...) 指定，
    以支持不同场景的 timeout 差异。
    """
    global _default_client
    if _default_client is None or _default_client.is_closed:
        _default_client = httpx.AsyncClient(
            limits=httpx.Limits(
                max_connections=max_connections,
                max_keepalive_connections=max_keepalive_connections,
            ),
            follow_redirects=follow_redirects,
        )
    return _default_client


async def aclose_async_client() -> None:
    """进程关闭时清理共享客户端连接池（lifespan shutdown 调用）。

    注意：SAE/uvicorn 多 worker 下，drain 期间仍有 in-flight 请求依赖共享 client，
    显式 aclose 会中断它们抛 5xx。生产关闭路径建议不调用本函数，由 OS 在进程退出时
    回收 TCP 连接。本函数保留供 standalone 显式关闭场景使用。
    """
    global _default_client
    if _default_client is not None:
        try:
            await _default_client.aclose()
        except Exception:
            pass
        _default_client = None


def configure_default_executor(*, max_workers: int | None = None) -> None:
    """扩大当前事件循环的默认 ThreadPoolExecutor（A5）。

    Python 3.12 默认 executor 上限 = min(32, cpu+4)。SAE 小规格实例（2vCPU→6 线程）
    下，asyncio.to_thread 的同步阻塞调用（oss2 大文件上传/openpyxl/base64/payment SDK）
    极易打满线程池，表现为请求延迟飙升但不报错（隐性饥饿）。

    在 lifespan startup 调用一次，把线程池上限拉到 max_workers（默认 64），防止饥饿。
    max_workers 可传 settings 配置项；未传或 <=0 时用默认 64。
    """
    import asyncio
    import os
    from concurrent.futures import ThreadPoolExecutor

    workers = max_workers
    if not workers or workers <= 0:
        workers = int(os.environ.get("DEFAULT_EXECUTOR_MAX_WORKERS", "64") or 64)
    try:
        loop = asyncio.get_running_loop()
        loop.set_default_executor(ThreadPoolExecutor(max_workers=workers))
    except RuntimeError:
        # 无运行中事件循环时跳过（启动顺序异常的兜底，不影响进程）
        pass

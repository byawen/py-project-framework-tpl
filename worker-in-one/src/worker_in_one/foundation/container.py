"""依赖注入容器模块"""

from typing import Optional
from injector import Injector

# 全局变量
_injector: Optional[Injector] = None


def set_injector(injector: Injector) -> None:
    """设置全局 Injector 实例"""
    global _injector
    _injector = injector


def get_injector() -> Injector:
    """获取全局 Injector 实例"""
    if _injector is None:
        raise RuntimeError("Injector not initialized. Call this after worker startup.")
    return _injector


__all__ = ["set_injector", "get_injector"]
"""异常处理器模块

全局异常处理器
"""
from fastapi import FastAPI
from services_common.exception_handlers import register_base_exception_handlers


def register_exception_handlers(app: FastAPI) -> None:
    """向 FastAPI 应用注册异常处理器"""
    register_base_exception_handlers(app)

"""异常处理器模块

全局异常处理器
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from services_common.exception_handlers import register_base_exception_handlers

async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """处理验证异常"""
    return JSONResponse(
        status_code=422,
        content={
            "error": "VALIDATION_ERROR",
            "message": "Request validation failed",
            "details": exc.errors(),
        },
    )

async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """处理通用异常"""
    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_ERROR",
            "message": "An internal error occurred",
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """向 FastAPI 应用注册异常处理器"""
    register_base_exception_handlers(app)

    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)

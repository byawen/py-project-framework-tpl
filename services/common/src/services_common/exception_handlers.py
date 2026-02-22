"""异常处理器模块

全局异常处理器
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from services_common.exceptions import BaseDomainException, BaseApplicationException


async def domain_exception_handler(request: Request, exc: BaseDomainException) -> JSONResponse:
    """处理领域异常"""
    return JSONResponse(
        status_code=400,
        content={
            "error": exc.code or "DOMAIN_ERROR",
            "message": exc.message,
        },
    )


async def application_exception_handler(request: Request, exc: BaseApplicationException) -> JSONResponse:
    """处理应用异常"""
    return JSONResponse(
        status_code=400,
        content={
            "error": exc.code or "APPLICATION_ERROR",
            "message": exc.message,
        },
    )


def register_base_exception_handlers(app: FastAPI) -> None:
    """向 FastAPI 应用注册异常处理器"""
    app.add_exception_handler(BaseDomainException, domain_exception_handler)
    app.add_exception_handler(BaseApplicationException, application_exception_handler)

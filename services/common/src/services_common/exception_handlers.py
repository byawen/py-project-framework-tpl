"""异常处理器模块

全局异常处理器
"""
import logging
import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from services_common.exceptions import BaseDomainException, BaseApplicationException
from services_common.response import ErrorResponse, ResponseCode, ResponseResult

logger = logging.getLogger(__name__)


def _is_dev_environment(request: Request) -> bool:
    """判断是否为开发环境"""
    try:
        settings = request.app.state.settings
        return settings.DEBUG
    except Exception:
        return os.getenv("ENVIRONMENT", "development") == "development"


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """处理 HTTPException 异常"""
    # 根据状态码映射到 ResponseResult
    result_map = {
        400: ResponseResult.BAD_REQUEST,
        401: ResponseResult.UNAUTHORIZED,
        403: ResponseResult.FORBIDDEN,
        404: ResponseResult.NOT_FOUND,
        409: ResponseResult.CONFLICT,
    }
    result = result_map.get(exc.status_code, ResponseResult.INTERNAL_ERROR)

    response = ErrorResponse(
        code=exc.status_code,
        result=result,
        message=exc.detail if isinstance(exc.detail, str) else "Error",
        detail=exc.detail if not isinstance(exc.detail, str) else None,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=response.model_dump(mode="json"),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """处理验证异常"""
    is_dev = _is_dev_environment(request)
    
    response = ErrorResponse(
        code=ResponseCode.UNPROCESSABLE_ENTITY,
        message="Request validation failed",
        detail=exc.errors() if is_dev else None,
    )
    return JSONResponse(
        status_code=ResponseCode.UNPROCESSABLE_ENTITY,
        content=response.model_dump(mode="json"),
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """处理通用异常"""
    is_dev = _is_dev_environment(request)
    
    logger.error(
        f"Unhandled exception: {exc}",
        exc_info=True,
        extra={
            "method": request.method,
            "path": request.url.path,
        }
    )
    
    if is_dev:
        response = ErrorResponse(
            code=ResponseCode.INTERNAL_SERVER_ERROR,
            message="Internal server error",
            detail=str(exc),
        )
    else:
        response = ErrorResponse(
            code=ResponseCode.INTERNAL_SERVER_ERROR,
            message="Internal server error",
            detail=None,
        )
    
    return JSONResponse(
        status_code=ResponseCode.INTERNAL_SERVER_ERROR,
        content=response.model_dump(mode="json"),
    )


async def domain_exception_handler(request: Request, exc: BaseDomainException) -> JSONResponse:
    """处理领域异常"""
    is_dev = _is_dev_environment(request)
    
    response = ErrorResponse(
        code=ResponseCode.BAD_REQUEST,
        message=exc.message,
        detail=exc.details if is_dev else None,
    )
    return JSONResponse(
        status_code=ResponseCode.BAD_REQUEST,
        content=response.model_dump(mode="json"),
    )


async def application_exception_handler(request: Request, exc: BaseApplicationException) -> JSONResponse:
    """处理应用异常"""
    is_dev = _is_dev_environment(request)
    
    response = ErrorResponse(
        code=ResponseCode.BAD_REQUEST,
        message=exc.message,
        detail=exc.details if is_dev else None,
    )
    return JSONResponse(
        status_code=ResponseCode.BAD_REQUEST,
        content=response.model_dump(mode="json"),
    )


def register_base_exception_handlers(app: FastAPI) -> None:
    """向 FastAPI 应用注册基础异常处理器"""
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
    app.add_exception_handler(BaseDomainException, domain_exception_handler)
    app.add_exception_handler(BaseApplicationException, application_exception_handler)

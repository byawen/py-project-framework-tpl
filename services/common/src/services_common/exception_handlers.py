"""异常处理器模块

全局异常处理器
"""
import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from services_common.exceptions import BaseDomainException, BaseApplicationException
from services_common.response import ErrorResponse, ResponseCode, ResponseResult


def _get_logger():
    """延迟导入，避免循环依赖。"""
    from services_common.logging import get_logger
    return get_logger(__name__)


def _sanitize_for_json(value):
    if isinstance(value, BaseException):
        return str(value)
    if isinstance(value, dict):
        return {key: _sanitize_for_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_json(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_for_json(item) for item in value]
    return value


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

    # 5xx 服务端错误：不向客户端暴露原始 detail，防止 SQL/堆栈泄露
    if exc.status_code >= 500:
        message = "Internal server error"
        detail = None
    else:
        message = exc.detail if isinstance(exc.detail, str) else "Error"
        detail = exc.detail if not isinstance(exc.detail, str) else None

    response = ErrorResponse(
        code=exc.status_code,
        result=result,
        message=message,
        detail=detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=response.model_dump(mode="json"),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """处理验证异常"""
    is_dev = _is_dev_environment(request)
    detail = _sanitize_for_json(exc.errors()) if is_dev else None
    
    response = ErrorResponse(
        code=ResponseCode.UNPROCESSABLE_ENTITY,
        message="Request validation failed",
        detail=detail,
    )
    return JSONResponse(
        status_code=ResponseCode.UNPROCESSABLE_ENTITY,
        content=response.model_dump(mode="json"),
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """处理通用异常"""
    logger = _get_logger()
    logger.error(
        f"Unhandled exception: {exc}",
        method=request.method,
        path=request.url.path,
        exc_info=True,
    )
    
    # 永远不向客户端暴露未处理异常的原始信息（可能包含 SQL、堆栈、连接串等）
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
    """处理领域异常 - 透传异常携带的 biz_code 到响应"""
    response = ErrorResponse(
        code=ResponseCode.BAD_REQUEST,
        biz_code=getattr(exc, "biz_code", 0),
        message=exc.message,
        detail=None,
    )
    return JSONResponse(
        status_code=ResponseCode.BAD_REQUEST,
        content=response.model_dump(mode="json"),
    )


async def application_exception_handler(request: Request, exc: BaseApplicationException) -> JSONResponse:
    """处理应用异常 - 透传异常携带的 biz_code 到响应"""
    response = ErrorResponse(
        code=ResponseCode.BAD_REQUEST,
        biz_code=getattr(exc, "biz_code", 0),
        message=exc.message,
        detail=None,
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

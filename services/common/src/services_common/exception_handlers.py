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


# ── 服务级 BizCode 映射注册表（all-in-one 多服务共用 app 时按路径前缀路由）──
# 各服务在自己的 setup() 中调用 register_service_bizcode_mapper 注册自己的前缀。
# mapper 签名: (http_status: int, exc: Exception) -> int  返回该服务的 biz_code。
# 未注册的服务 _resolve_bizcode 返回 0（保持原默认行为，向后兼容）。
_SERVICE_BIZCODE_MAPPERS: list[tuple[str, callable]] = []


def register_service_bizcode_mapper(prefix: str, mapper) -> None:
    """服务在 setup() 时注册自己的路径前缀与 BizCode 映射器。

    Args:
        prefix: 服务路由前缀，如 "/api/v1/skill-provider"（请求路径以此开头则命中该服务）
        mapper: 可调用对象 (http_status: int, exc: Exception) -> int，返回服务级 biz_code
    """
    _SERVICE_BIZCODE_MAPPERS.append((prefix, mapper))


def _resolve_bizcode(request: Request, http_status: int, exc: Exception) -> int:
    """按请求路径前缀查服务级 BizCode；未匹配返回 0（走原默认，向后兼容）。"""
    path = request.url.path
    for prefix, mapper in _SERVICE_BIZCODE_MAPPERS:
        if path.startswith(prefix):
            try:
                return int(mapper(http_status, exc))
            except Exception:
                return 0
    return 0


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
        biz_code=_resolve_bizcode(request, exc.status_code, exc),
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
        biz_code=_resolve_bizcode(request, ResponseCode.UNPROCESSABLE_ENTITY, exc),
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
        biz_code=_resolve_bizcode(request, ResponseCode.INTERNAL_SERVER_ERROR, exc),
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

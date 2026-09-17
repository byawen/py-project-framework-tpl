"""异常处理器模块

全局异常处理器
"""
import os
from typing import Optional
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from services_common.exceptions import BaseDomainException, BaseApplicationException
from http import HTTPStatus
from services_common.response import ErrorResponse, ResponseResult


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
    """按请求路径前缀查服务级 BizCode；未匹配返回 0（走原默认，向后兼容）。

    采用「最长前缀匹配」：当多个服务前缀都能命中同一请求路径时（例如 payment 的
    /api/v1 与 account 的 /api/v1/account 都能匹配 /api/v1/account/x），选择最长的
    （最具体的）前缀，避免宽前缀服务污染窄前缀服务的 HTTPException biz_code。
    这对本身前缀唯一的服务无任何影响（仍是唯一命中），仅修正宽前缀共存场景。
    """
    path = request.url.path
    best_prefix = None
    best_mapper = None
    for prefix, mapper in _SERVICE_BIZCODE_MAPPERS:
        if path.startswith(prefix) and (best_prefix is None or len(prefix) > len(best_prefix)):
            best_prefix = prefix
            best_mapper = mapper
    if best_mapper is None:
        return 0
    try:
        return int(best_mapper(http_status, exc))
    except Exception:
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
        HTTPStatus.BAD_REQUEST: ResponseResult.BAD_REQUEST,
        HTTPStatus.UNAUTHORIZED: ResponseResult.UNAUTHORIZED,
        HTTPStatus.FORBIDDEN: ResponseResult.FORBIDDEN,
        HTTPStatus.NOT_FOUND: ResponseResult.NOT_FOUND,
        HTTPStatus.CONFLICT: ResponseResult.CONFLICT,
        HTTPStatus.REQUEST_ENTITY_TOO_LARGE: ResponseResult.REQUEST_ENTITY_TOO_LARGE,
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
        code=HTTPStatus.UNPROCESSABLE_ENTITY,
        biz_code=_resolve_bizcode(request, HTTPStatus.UNPROCESSABLE_ENTITY, exc),
        message="Request validation failed",
        detail=detail,
    )
    return JSONResponse(
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
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
        code=HTTPStatus.INTERNAL_SERVER_ERROR,
        biz_code=_resolve_bizcode(request, HTTPStatus.INTERNAL_SERVER_ERROR, exc),
        message="Internal server error",
        detail=None,
    )
    
    return JSONResponse(
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        content=response.model_dump(mode="json"),
    )


# 领域/应用异常的 HTTP 状态码 → ResponseResult 映射
# 异常可通过 status_code 属性指定非 400 状态（如频控 429、文件过大 413），
# handler 据此映射 result；未覆盖的状态码回退到 BAD_REQUEST。
_DOMAIN_APP_RESULT_MAP = {
    HTTPStatus.BAD_REQUEST: ResponseResult.BAD_REQUEST,
    HTTPStatus.CONFLICT: ResponseResult.CONFLICT,
    HTTPStatus.REQUEST_ENTITY_TOO_LARGE: ResponseResult.REQUEST_ENTITY_TOO_LARGE,
    HTTPStatus.TOO_MANY_REQUESTS: ResponseResult.BAD_REQUEST,
    HTTPStatus.INTERNAL_SERVER_ERROR: ResponseResult.INTERNAL_ERROR,
    HTTPStatus.BAD_GATEWAY: ResponseResult.SERVICE_UNAVAILABLE,
    HTTPStatus.SERVICE_UNAVAILABLE: ResponseResult.SERVICE_UNAVAILABLE,
}


def _domain_app_response(exc, default_result: ResponseResult) -> ErrorResponse:
    """领域/应用异常 → ErrorResponse：透传 biz_code、payload，按 status_code 映射 result。

    payload 写入独立 payload 字段（与 detail 分工，互不覆盖）；detail 保持 None
    （领域/应用异常不写调试详情）。status_code 驱动 HTTP 状态码与 result（默认 400）。
    """
    http_status = getattr(exc, "status_code", HTTPStatus.BAD_REQUEST)
    result = _DOMAIN_APP_RESULT_MAP.get(http_status, default_result)
    return ErrorResponse(
        code=http_status,
        biz_code=getattr(exc, "biz_code", 0),
        result=result,
        message=exc.message,
        detail=None,
        payload=getattr(exc, "payload", None),
    )


def _retry_after_header(exc, http_status: int) -> Optional[dict]:
    """若异常 payload 含 retry_after 且状态码 429（TOO_MANY_REQUESTS），返回 Retry-After 响应头。

    通用机制：任何携带 payload={"retry_after": N} 的 429 异常自动带上该头，
    无需为每种频控异常单独注册处理器或构造响应。
    """
    payload = getattr(exc, "payload", None)
    if http_status == HTTPStatus.TOO_MANY_REQUESTS and isinstance(payload, dict) and payload.get("retry_after") is not None:
        return {"Retry-After": str(payload["retry_after"])}
    return None


async def domain_exception_handler(request: Request, exc: BaseDomainException) -> JSONResponse:
    """处理领域异常 - 透传异常携带的 biz_code、payload、status_code 到响应

    payload 为异常构造时携带的结构化数据（如 {"retry_after": 58}），自动写入响应体
    payload 字段（与 detail 分工独立），供前端展示。status_code 驱动 HTTP 状态码
    （默认 400，可覆盖为 429/413 等）。无需为每种异常单独注册处理器。
    """
    response = _domain_app_response(exc, ResponseResult.BAD_REQUEST)
    return JSONResponse(
        status_code=response.code,
        content=response.model_dump(mode="json"),
        headers=_retry_after_header(exc, response.code),
    )


async def application_exception_handler(request: Request, exc: BaseApplicationException) -> JSONResponse:
    """处理应用异常 - 透传异常携带的 biz_code、payload、status_code 到响应

    payload 为异常构造时携带的结构化数据（如 {"retry_after": 58}、{"max_size": 1048576}），
    自动写入响应体 payload 字段（与 detail 分工独立），供前端展示。status_code 驱动
    HTTP 状态码（默认 400，可覆盖为 429/413 等）。无需为每种异常单独注册处理器。
    """
    response = _domain_app_response(exc, ResponseResult.BAD_REQUEST)
    return JSONResponse(
        status_code=response.code,
        content=response.model_dump(mode="json"),
        headers=_retry_after_header(exc, response.code),
    )


def register_base_exception_handlers(app: FastAPI) -> None:
    """向 FastAPI 应用注册基础异常处理器"""
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
    app.add_exception_handler(BaseDomainException, domain_exception_handler)
    app.add_exception_handler(BaseApplicationException, application_exception_handler)

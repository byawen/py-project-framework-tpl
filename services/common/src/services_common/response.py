"""API 响应统一格式模块

提供标准的 API 响应格式，包含成功响应、错误响应、分页响应等。
"""

from datetime import datetime
from enum import Enum
from typing import Any, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

# 泛型类型
T = TypeVar("T")

# 默认 API 版本
DEFAULT_API_VERSION = "v1"


class ResponseResult(str, Enum):
    """响应结果枚举 - 用于标识请求结果类型"""

    # 成功
    SUCCESS = "success"
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"

    # 客户端错误
    BAD_REQUEST = "error.bad_request"
    UNAUTHORIZED = "error.unauthorized"
    FORBIDDEN = "error.forbidden"
    NOT_FOUND = "error.not_found"
    CONFLICT = "error.conflict"
    VALIDATION_ERROR = "error.validation"

    # 服务器错误
    INTERNAL_ERROR = "error.internal"
    SERVICE_UNAVAILABLE = "error.service_unavailable"


class ResponseCode:
    """响应状态码常量"""
    
    # 成功
    SUCCESS = 200
    CREATED = 201
    NO_CONTENT = 204
    
    # 客户端错误
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    CONFLICT = 409
    UNPROCESSABLE_ENTITY = 422
    
    # 服务器错误
    INTERNAL_SERVER_ERROR = 500
    SERVICE_UNAVAILABLE = 503


class BaseResponse(BaseModel):
    """基础响应模型
    
    字段说明:
        api_version: API 版本标识
        result: 响应结果类型（success / error.xxx）
        code: HTTP 状态码（200/400/500 等，反映传输层语义）
        biz_code: 业务码（8位整数，精确定位服务+业务场景，成功响应也携带）
        message: 人类可读的响应消息
        timestamp: 响应时间戳
    """
    
    api_version: str = Field(default=DEFAULT_API_VERSION, description="API 版本")
    result: ResponseResult = Field(default=ResponseResult.SUCCESS, description="响应结果标识")
    code: int = Field(default=ResponseCode.SUCCESS, description="HTTP 状态码")
    biz_code: int = Field(default=0, description="业务码（8位整数，定位服务+业务场景）")
    message: str = Field(default="Success", description="响应消息")
    timestamp: datetime = Field(default_factory=datetime.now, description="响应时间戳")
    
    class Config:
        json_schema_extra = {
            "example": {
                "api_version": "v1",
                "result": "success",
                "code": 200,
                "biz_code": 0,
                "message": "Success",
                "timestamp": "2024-01-01T00:00:00Z"
            }
        }


class DataResponse(BaseResponse, Generic[T]):
    """数据响应模型 - 用于单个数据项"""
    
    data: Optional[T] = Field(default=None, description="响应数据")
    
    class Config:
        json_schema_extra = {
            "example": {
                "api_version": "v1",
                "result": "success",
                "code": 200,
                "message": "Success",
                "timestamp": "2024-01-01T00:00:00Z",
                "data": {"id": 1, "name": "example"}
            }
        }


class ListResponse(BaseResponse, Generic[T]):
    """列表响应模型 - 用于数据列表"""
    
    data: List[T] = Field(default_factory=list, description="数据列表")
    total: int = Field(default=0, description="总数量")
    
    class Config:
        json_schema_extra = {
            "example": {
                "api_version": "v1",
                "result": "success",
                "code": 200,
                "message": "Success",
                "timestamp": "2024-01-01T00:00:00Z",
                "data": [{"id": 1, "name": "item1"}],
                "total": 1
            }
        }


class PageResponse(BaseResponse, Generic[T]):
    """分页响应模型 - 用于分页数据"""
    
    data: List[T] = Field(default_factory=list, description="数据列表")
    page: int = Field(default=1, description="当前页码")
    page_size: int = Field(default=20, description="每页数量")
    total: int = Field(default=0, description="总数量")
    total_pages: int = Field(default=0, description="总页数")
    
    class Config:
        json_schema_extra = {
            "example": {
                "api_version": "v1",
                "result": "success",
                "code": 200,
                "message": "Success",
                "timestamp": "2024-01-01T00:00:00Z",
                "data": [{"id": 1, "name": "item1"}],
                "page": 1,
                "page_size": 20,
                "total": 1,
                "total_pages": 1
            }
        }


class ErrorResponse(BaseResponse):
    """错误响应模型"""
    
    code: int = Field(default=ResponseCode.INTERNAL_SERVER_ERROR, description="HTTP 错误状态码")
    biz_code: int = Field(default=0, description="业务码（8位整数，定位服务+业务场景）")
    result: ResponseResult = Field(default=ResponseResult.INTERNAL_ERROR, description="响应结果标识")
    message: str = Field(default="Internal Server Error", description="错误消息")
    detail: Optional[Any] = Field(default=None, description="详细错误信息")
    trace_id: Optional[str] = Field(default=None, description="请求追踪ID")
    
    class Config:
        json_schema_extra = {
            "example": {
                "api_version": "v1",
                "result": "error.internal",
                "code": 500,
                "biz_code": 99000000,
                "message": "Internal Server Error",
                "timestamp": "2024-01-01T00:00:00Z",
                "detail": "Database connection failed",
                "trace_id": "abc123"
            }
        }


# ============================================================
# 响应构建函数
# ============================================================

def success(
    data: Any = None,
    message: str = "Success",
    result: ResponseResult = ResponseResult.SUCCESS,
    biz_code: int = 0,
) -> DataResponse:
    """构建成功响应
    
    Args:
        data: 响应数据
        message: 响应消息
        result: 响应结果标识
        biz_code: 业务码（默认 0 表示通用成功，可传入服务特定的成功码）
        
    Returns:
        DataResponse 实例
    """
    return DataResponse(
        api_version=DEFAULT_API_VERSION,
        result=result,
        code=ResponseCode.SUCCESS,
        biz_code=biz_code,
        message=message,
        data=data,
    )


def created(
    data: Any = None,
    message: str = "Created successfully",
    result: ResponseResult = ResponseResult.CREATED,
    biz_code: int = 0,
) -> DataResponse:
    """构建创建成功响应
    
    Args:
        data: 响应数据
        message: 响应消息
        result: 响应结果标识
        biz_code: 业务码
        
    Returns:
        DataResponse 实例
    """
    return DataResponse(
        api_version=DEFAULT_API_VERSION,
        result=result,
        code=ResponseCode.CREATED,
        biz_code=biz_code,
        message=message,
        data=data,
    )


def list_response(
    data: List[Any],
    total: int = 0,
    message: str = "Success",
    result: ResponseResult = ResponseResult.SUCCESS,
    biz_code: int = 0,
) -> ListResponse:
    """构建列表响应
    
    Args:
        data: 数据列表
        total: 总数量
        message: 响应消息
        result: 响应结果标识
        biz_code: 业务码
        
    Returns:
        ListResponse 实例
    """
    return ListResponse(
        api_version=DEFAULT_API_VERSION,
        result=result,
        code=ResponseCode.SUCCESS,
        biz_code=biz_code,
        message=message,
        data=data,
        total=total,
    )


def page_response(
    data: List[Any],
    page: int = 1,
    page_size: int = 20,
    total: int = 0,
    message: str = "Success",
    result: ResponseResult = ResponseResult.SUCCESS,
    biz_code: int = 0,
) -> PageResponse:
    """构建分页响应
    
    Args:
        data: 数据列表
        page: 当前页码
        page_size: 每页数量
        total: 总数量
        message: 响应消息
        result: 响应结果标识
        biz_code: 业务码
        
    Returns:
        PageResponse 实例
    """
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    
    return PageResponse(
        api_version=DEFAULT_API_VERSION,
        result=result,
        code=ResponseCode.SUCCESS,
        biz_code=biz_code,
        message=message,
        data=data,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


def error(
    message: str = "Internal Server Error",
    code: int = ResponseCode.INTERNAL_SERVER_ERROR,
    detail: Any = None,
    trace_id: Optional[str] = None,
    result: ResponseResult = ResponseResult.INTERNAL_ERROR,
    biz_code: int = 0,
) -> ErrorResponse:
    """构建错误响应
    
    Args:
        message: 错误消息
        code: HTTP 错误状态码
        detail: 详细错误信息
        trace_id: 请求追踪ID
        result: 响应结果标识
        biz_code: 业务码（精确定位服务+业务场景）
        
    Returns:
        ErrorResponse 实例
    """
    return ErrorResponse(
        api_version=DEFAULT_API_VERSION,
        result=result,
        code=code,
        biz_code=biz_code,
        message=message,
        detail=detail,
        trace_id=trace_id,
    )


def bad_request(message: str = "Bad Request", detail: Any = None, biz_code: int = 0) -> ErrorResponse:
    """构建 400 错误响应 - 请求参数格式错误或缺失"""
    return error(
        message=message,
        code=ResponseCode.BAD_REQUEST,
        detail=detail,
        result=ResponseResult.BAD_REQUEST,
        biz_code=biz_code,
    )


def unauthorized(message: str = "Unauthorized", detail: Any = None, biz_code: int = 0) -> ErrorResponse:
    """构建 401 错误响应 - 未登录或认证信息缺失"""
    return error(
        message=message,
        code=ResponseCode.UNAUTHORIZED,
        detail=detail,
        result=ResponseResult.UNAUTHORIZED,
        biz_code=biz_code,
    )


def forbidden(message: str = "Forbidden", detail: Any = None, biz_code: int = 0) -> ErrorResponse:
    """构建 403 错误响应 - 已认证但无权限访问该资源"""
    return error(
        message=message,
        code=ResponseCode.FORBIDDEN,
        detail=detail,
        result=ResponseResult.FORBIDDEN,
        biz_code=biz_code,
    )


def not_found(message: str = "Not Found", detail: Any = None, biz_code: int = 0) -> ErrorResponse:
    """构建 404 错误响应 - 请求的资源不存在"""
    return error(
        message=message,
        code=ResponseCode.NOT_FOUND,
        detail=detail,
        result=ResponseResult.NOT_FOUND,
        biz_code=biz_code,
    )


def conflict(message: str = "Conflict", detail: Any = None, biz_code: int = 0) -> ErrorResponse:
    """构建 409 错误响应 - 资源冲突（重复创建、状态冲突）"""
    return error(
        message=message,
        code=ResponseCode.CONFLICT,
        detail=detail,
        result=ResponseResult.CONFLICT,
        biz_code=biz_code,
    )

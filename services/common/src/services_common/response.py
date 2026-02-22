"""API 响应统一格式模块

提供标准的 API 响应格式，包含成功响应、错误响应、分页响应等。
"""

from datetime import datetime
from typing import Any, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

# 泛型类型
T = TypeVar("T")


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
    """基础响应模型"""
    
    code: int = Field(default=ResponseCode.SUCCESS, description="响应状态码")
    message: str = Field(default="Success", description="响应消息")
    timestamp: datetime = Field(default_factory=datetime.now, description="响应时间戳")
    
    class Config:
        json_schema_extra = {
            "example": {
                "code": 200,
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
    
    code: int = Field(default=ResponseCode.INTERNAL_SERVER_ERROR, description="错误状态码")
    message: str = Field(default="Internal Server Error", description="错误消息")
    detail: Optional[Any] = Field(default=None, description="详细错误信息")
    trace_id: Optional[str] = Field(default=None, description="请求追踪ID")
    
    class Config:
        json_schema_extra = {
            "example": {
                "code": 500,
                "message": "Internal Server Error",
                "timestamp": "2024-01-01T00:00:00Z",
                "detail": "Database connection failed",
                "trace_id": "abc123"
            }
        }


# ============================================================
# 响应构建函数
# ============================================================

def success(data: Any = None, message: str = "Success") -> DataResponse:
    """构建成功响应
    
    Args:
        data: 响应数据
        message: 响应消息
        
    Returns:
        DataResponse 实例
    """
    return DataResponse(
        code=ResponseCode.SUCCESS,
        message=message,
        data=data,
    )


def created(data: Any = None, message: str = "Created successfully") -> DataResponse:
    """构建创建成功响应
    
    Args:
        data: 响应数据
        message: 响应消息
        
    Returns:
        DataResponse 实例
    """
    return DataResponse(
        code=ResponseCode.CREATED,
        message=message,
        data=data,
    )


def list_response(data: List[Any], total: int = 0, message: str = "Success") -> ListResponse:
    """构建列表响应
    
    Args:
        data: 数据列表
        total: 总数量
        message: 响应消息
        
    Returns:
        ListResponse 实例
    """
    return ListResponse(
        code=ResponseCode.SUCCESS,
        message=message,
        data=data,
        total=total,
    )


def page_response(
    data: List[Any],
    page: int = 1,
    page_size: int = 20,
    total: int = 0,
    message: str = "Success"
) -> PageResponse:
    """构建分页响应
    
    Args:
        data: 数据列表
        page: 当前页码
        page_size: 每页数量
        total: 总数量
        message: 响应消息
        
    Returns:
        PageResponse 实例
    """
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    
    return PageResponse(
        code=ResponseCode.SUCCESS,
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
) -> ErrorResponse:
    """构建错误响应
    
    Args:
        message: 错误消息
        code: 错误状态码
        detail: 详细错误信息
        trace_id: 请求追踪ID
        
    Returns:
        ErrorResponse 实例
    """
    return ErrorResponse(
        code=code,
        message=message,
        detail=detail,
        trace_id=trace_id,
    )


def bad_request(message: str = "Bad Request", detail: Any = None) -> ErrorResponse:
    """构建 400 错误响应"""
    return error(message=message, code=ResponseCode.BAD_REQUEST, detail=detail)


def unauthorized(message: str = "Unauthorized", detail: Any = None) -> ErrorResponse:
    """构建 401 错误响应"""
    return error(message=message, code=ResponseCode.UNAUTHORIZED, detail=detail)


def forbidden(message: str = "Forbidden", detail: Any = None) -> ErrorResponse:
    """构建 403 错误响应"""
    return error(message=message, code=ResponseCode.FORBIDDEN, detail=detail)


def not_found(message: str = "Not Found", detail: Any = None) -> ErrorResponse:
    """构建 404 错误响应"""
    return error(message=message, code=ResponseCode.NOT_FOUND, detail=detail)


def conflict(message: str = "Conflict", detail: Any = None) -> ErrorResponse:
    """构建 409 错误响应"""
    return error(message=message, code=ResponseCode.CONFLICT, detail=detail)

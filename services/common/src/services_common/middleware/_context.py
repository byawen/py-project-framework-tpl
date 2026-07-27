"""中间件上下文变量 - 从根级 _context 转发，保持向后兼容。"""
from services_common._context import request_id_context, get_request_id

__all__ = ["request_id_context", "get_request_id"]

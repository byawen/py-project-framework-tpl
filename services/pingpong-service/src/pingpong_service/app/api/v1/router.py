"""PingPong 服务 API 路由模块

所有路由聚合点 prefix="/v1"
"""
from fastapi import APIRouter

from pingpong_service.app.api.v1.endpoints import pp_demo

api_router = APIRouter(prefix="/v1/pingpong")

# 包含端点路由
api_router.include_router(pp_demo.router)
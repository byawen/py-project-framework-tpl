"""Ping Pong API 端点

Ping/Pong API 端点
"""
from fastapi import APIRouter, Depends
from pingpong_service.foundation.container import get_injector
from pingpong_service.app.api.v1.schemas.ping_pong import (
    PingResponse,
    PingDataResponse,
    PongRequest,
    PongResponse,
    PongDataResponse,
)
from pingpong_service.app.application.queries.get_ping import PingQuery
from pingpong_service.app.application.commands.create_pong import PongCommand
from services_common.response import success

router = APIRouter(prefix="/pingpong", tags=["pingpong"])

def get_ping_query() -> PingQuery:
    """获取 PingQuery 实例"""
    injector = get_injector()
    return injector.get(PingQuery)


def get_pong_command() -> PongCommand:
    """获取 PongCommand 实例"""
    injector = get_injector()
    return injector.get(PongCommand)


@router.get("/ping", response_model=PingDataResponse)
async def ping(
    query: PingQuery = Depends(get_ping_query),
) -> PingDataResponse:
    """Ping 端点 - 返回 'ping, xxxxxx'"""
    result = await query.execute()
    ping_data = PingResponse(
        message=result.message,
        ping_id=result.ping.id if result.ping else None,
        created_at=result.ping.created_at if result.ping else None,
    )
    return success(data=ping_data, message="Ping successful")


@router.post("/pong", response_model=PongDataResponse)
async def pong(
    request: PongRequest,
    command: PongCommand = Depends(get_pong_command),
) -> PongDataResponse:
    """Pong 端点 - 提交 {"data": "xxxxx"}"""
    result = await command.execute(request.data)
    pong_data = PongResponse(
        data=result.data,
        pong_id=result.pong.id if result.pong else None,
        created_at=result.pong.created_at if result.pong else None,
    )
    return success(data=pong_data, message="Pong created successfully")
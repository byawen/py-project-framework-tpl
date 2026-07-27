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
from pingpong_service.app.application.queries.biz_code_test import BizCodeTestQuery
from pingpong_service.app.application.commands.create_pong import PongCommand
from pingpong_service.foundation.logging import get_logger
from services_common.response import success, DataResponse

router = APIRouter(prefix="/ping-pong", tags=["ping-pong"])
logger = get_logger(__name__)

def get_ping_query() -> PingQuery:
    """获取 PingQuery 实例"""
    injector = get_injector()
    return injector.get(PingQuery)


def get_pong_command() -> PongCommand:
    """获取 PongCommand 实例"""
    injector = get_injector()
    return injector.get(PongCommand)


@router.get("/ping", response_model=DataResponse[PingDataResponse])
async def ping(
    query: PingQuery = Depends(get_ping_query),
) -> DataResponse[PingDataResponse]:
    """Ping 端点 - 返回 'ping, xxxxxx'"""
    logger.info(f"Pingpong ping requested")
    result = await query.execute()
    ping_data = PingResponse(
        message=result.message,
        ping_id=result.ping.ping_id if result.ping else None,
        created_at=result.ping.created_at if result.ping else None,
    )
    return success(data=ping_data, message="Ping successful")


@router.post("/pong", response_model=DataResponse[PongDataResponse])
async def pong(
    request: PongRequest,
    command: PongCommand = Depends(get_pong_command),
) -> DataResponse[PongDataResponse]:
    """Pong 端点 - 提交 {"data": "xxxxx"}"""
    logger.info(f"Pingpong pong requested")
    result = await command.execute(request.data)
    pong_data = PongResponse(
        data=result.data,
        pong_id=result.pong.pong_id if result.pong else None,
        created_at=result.pong.created_at if result.pong else None,
    )
    return success(data=pong_data, message="Pong created successfully")


def get_biz_code_test_query() -> BizCodeTestQuery:
    """获取 BizCodeTestQuery 实例"""
    injector = get_injector()
    return injector.get(BizCodeTestQuery)


@router.get("/biz-code-test")
async def biz_code_test(
    query: BizCodeTestQuery = Depends(get_biz_code_test_query),
):
    """业务码测试端点 - 通过 application 层抛出异常，验证 biz_code 透传到响应"""
    await query.execute()
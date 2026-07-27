"""X-API-Key 校验依赖"""
from fastapi import Header, HTTPException, status


async def require_api_token(x_api_token: str = Header(..., alias="X-API-Key")) -> None:
    pass
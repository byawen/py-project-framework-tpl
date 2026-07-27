"""JWT 安全工具模块

JWT Token 生成和验证
"""
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import jwt
from fastapi import Header, HTTPException, status
from jose import JWTError

from services_common import logging
from services_common.exceptions import InvalidTokenException, TokenExpiredException


######################

def create_token(data: Dict[str, Any], expires_minute: int = 30, secret_key: str = "secret-key", algorithm: str = "HS256") -> str:
    """创建 JWT Token"""
    to_encode = data.copy()
    expire = datetime.now() + timedelta(minutes=expires_minute)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, secret_key, algorithm=algorithm)

def decode_token(token: str, secret_key: str = "secret-key", algorithm: str = "HS256") -> dict[str, Any]:
    """解析 JWT Token"""
    try:
        return jwt.decode(token, secret_key, algorithm=algorithm)
    except jwt.ExpiredSignatureError:
        raise TokenExpiredException()
    except jwt.InvalidTokenError:
        raise InvalidTokenException()


######################### 以下为通用组 #########################
# 目前授权通用放在 common-service 中，后期再扩展 auth-service 和 gateway api 网关服务

def generate_token(account_id: str, expires_minute: int = 30, token_type: str = "access", secret_key: str = "secret-key", algorithm: str = "HS256") -> tuple[str, int]:
    """生成 JWT Token"""
    expire_at = int((datetime.now() + timedelta(minutes=expires_minute)).timestamp())
    payload = {
        "sub": account_id,
        "iss": "01",
        "type": token_type,
        "exp": expire_at,
    }
    token = jwt.encode(payload, secret_key, algorithm=algorithm)
    return token, expire_at


def parse_token(token: str, token_type: str = "access", secret_key: str = "secret-key", algorithm: str = "HS256") -> Any:
    """解析 JWT Token"""
    try:
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        type = payload.get("type")
        if token_type == type:
            return payload
        raise InvalidTokenException()
    except jwt.ExpiredSignatureError:
        raise TokenExpiredException()
    except jwt.InvalidTokenError:
        raise InvalidTokenException()


async def parse_token_account_id(authorization: str, token_type: str = "access", secret_key: str = "secret-key", algorithm: str = "HS256") -> str:
    """解析 Token 并返回账号 ID"""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未授权，请先登录",
        )

    # 移除 "Bearer " 前缀
    if authorization.startswith("Bearer "):
        token = authorization[7:]
    else:
        token = authorization

    try:
        # 解析 token
        payload = parse_token(token, token_type, secret_key, algorithm)
        account_id = payload.get("sub")
        if not account_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的 token",
            )
        return account_id
    except TokenExpiredException:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录已过期，请重新登录",
        )
    except InvalidTokenException:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 token",
        )
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 token 格式",
        )


async def try_parse_token_account_id(authorization: str, token_type: str = "access", secret_key: str = "secret-key", algorithm: str = "HS256") -> str:
    """尝试解析 Token 并返回账号 ID"""
    if not authorization:
        return ""

    # 移除 "Bearer " 前缀
    if authorization.startswith("Bearer "):
        token = authorization[7:]
    else:
        token = authorization

    try:
        # 解析 token
        payload = parse_token(token, token_type, secret_key, algorithm)
        account_id = payload.get("sub")
        if not account_id:
            return ""
        return account_id
    except Exception:
        return ""
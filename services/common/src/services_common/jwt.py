"""JWT 安全工具模块

JWT Token 生成和验证
"""
from datetime import datetime, timedelta
from typing import Any

import jwt
from fastapi import Header, HTTPException, status

from services_common.exceptions import InvalidTokenException, TokenExpiredException


def generate_token(account_id: str, expires_days: int = 30, secret_key: str = "secret-key") -> tuple[str, int]:
    """生成 JWT Token

    Args:
        account_id: 账号 ID
        expires_days: 过期天数，默认30天

    Returns:
        tuple: (token字符串, 过期时间戳)
    """
    expire_at = int((datetime.now() + timedelta(days=expires_days)).timestamp())
    payload = {
        "sub": account_id,
        "iss": "llmops",
        "exp": expire_at,
    }
    token = jwt.encode(payload, secret_key, algorithm="HS256")
    return token, expire_at


def parse_token(token: str, secret_key: str = "secret-key") -> dict[str, Any]:
    """解析 JWT Token

    Args:
        token: JWT Token 字符串
        secret_key: 密钥

    Returns:
        dict: Token 载荷

    Raises:
        InvalidTokenException: Token 无效
        TokenExpiredException: Token 已过期
    """
    try:
        return jwt.decode(token, secret_key, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise TokenExpiredException()
    except jwt.InvalidTokenError:
        raise InvalidTokenException()


async def parse_token_account_id(authorization: str, secret_key: str = "secret-key") -> str:
    """解析 Token 并返回账号 ID

    Args:
        authorization: Authorization header
        secret_key: 密钥

    Returns:
        str: 账号 ID

    Raises:
        HTTPException: 未授权或 token 无效
    """
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
        payload = parse_token(token, secret_key)
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

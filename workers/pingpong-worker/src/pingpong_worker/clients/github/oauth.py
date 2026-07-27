"""Github OAuth API 客户端"""

import httpx
from pingpong_worker.foundation.config import Settings


class GithubOauthAPIClient:
    """Github OAuth API 客户端"""

    def __init__(self):
        self.base_url = "https://github.com"

    async def get_access_token(self, code: str) -> dict:
        """获取 Access Token"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/login/oauth/access_token",
                json={"code": code},
                headers={"Accept": "application/json"},
            )
            return response.json()

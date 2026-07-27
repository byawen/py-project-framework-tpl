"""Test API Client Tests

外部服务客户端测试
"""
import pytest
from pingpong_service.clients.github import GithubOauthAPIClient
from pingpong_service.foundation.container import get_injector


@pytest.mark.asyncio
async def test_request():
    """测试 test_request() 返回 'external request data ...'"""
    injector = get_injector()
    client = injector.get(GithubOauthAPIClient)
    result = await client.oauth_request()
    assert result == "external request data ..."

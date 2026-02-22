"""GitHub OAuth 客户端模块

外部服务客户端 - GitHub OAuth API
"""
from injector import inject

from pingpong_service.foundation.config import Settings
from pingpong_service.foundation.logging import LogHelper, LogManager

class GithubOauthAPIClient:
    """GitHub OAuth API 客户端"""
    @inject
    def __init__(self, setting: Settings, log_manager: LogManager):
        self.logger: LogHelper = log_manager.get_logger(__name__)
        self.base_url = setting.GITHUB_SERVICE_URL or "http://localhost:8001"

    async def oauth_request(self) -> str:
        """测试请求 - 返回 'external request data ...'"""
        self.logger.info("Executing Ping query")
        # 这里模拟一个外部 API 调用
        return "external request data ..."

"""External Service Clients Package

外部服务客户端统一放这里
"""
from pingpong_service.clients.github import GithubOauthAPIClient
from pingpong_service.app.application.modules import ApplicationModule

__all__ = ["ApplicationModule", "GithubOauthAPIClient"]
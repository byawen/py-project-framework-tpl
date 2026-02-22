"""External Service Clients Package

外部服务客户端统一放这里
"""
from pingpong_service.clients.github import GithubOauthAPIClient
from pingpong_service.clients.other_service import UserService
from pingpong_service.app.application.modules import ApplicationModule

__all__ = ["ApplicationModule", "UserService", "GithubOauthAPIClient"]
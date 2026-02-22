"""Repositories Package"""
from pingpong_service.app.domain.repositories.ping_repository import PingRepository
from pingpong_service.app.domain.repositories.pong_repository import PongRepository

__all__ = ["PingRepository", "PongRepository"]

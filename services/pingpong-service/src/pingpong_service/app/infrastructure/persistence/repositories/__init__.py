"""Repositories Package"""
from pingpong_service.app.infrastructure.persistence.repositories.sql_ping_repository import SQLPingRepository
from pingpong_service.app.infrastructure.persistence.repositories.sql_pong_repository import SQLPongRepository

__all__ = ["SQLPingRepository", "SQLPongRepository"]

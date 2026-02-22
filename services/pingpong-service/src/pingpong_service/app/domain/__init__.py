"""Domain Layer Package

Domain Layer - 核心领域层（最纯净）

包含:
- entities: 实体 / 聚合根
- repositories: 仓储接口（抽象）
- value_objects: 值对象（不可变）
- exceptions: 领域规则异常
"""

# Entities
from pingpong_service.app.domain.entities.ping import Ping, Pong

# Repository interfaces
from pingpong_service.app.domain.repositories.ping_repository import PingRepository
from pingpong_service.app.domain.repositories.pong_repository import PongRepository

# Value objects
from pingpong_service.app.domain.value_objects.ping_message import PingMessage
from pingpong_service.app.domain.value_objects.pong_data import PongData

# Modules
from pingpong_service.app.domain.modules import DomainModule

__all__ = [
    # Entities
    "Ping",
    "Pong",
    # Repositories
    "PingRepository",
    "PongRepository",
    # Value objects
    "PingMessage",
    "PongData",
    # Module
    "DomainModule"
]

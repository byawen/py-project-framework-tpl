"""Commands Package

命令处理器(写)
"""
from pingpong_service.app.application.commands.create_pong import PongCommand, PongCommandResult

__all__ = ["PongCommand", "PongCommandResult"]
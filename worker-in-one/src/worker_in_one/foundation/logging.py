"""日志模块 - 基于 common 的日志封装，支持 @inject 注入"""

from functools import lru_cache

from injector import inject, Inject
from workers_common.logging import Logger as BaseLogger


class LogManager:
    """日志管理器 - 用于创建带名称的日志记录器, 此类支持依赖注入"""

    @inject
    def __init__(self) -> None:
        """初始化日志管理器"""
        self._loggers: dict[str, BaseLogger] = {}

    def get_logger(self, name: str) -> BaseLogger:
        """获取指定名称的日志记录器"""
        if name not in self._loggers:
            self._loggers[name] = BaseLogger(name)
        return self._loggers[name]


@lru_cache
def get_log_manager() -> LogManager:
    """获取日志管理器单例（用于非注入场景）"""
    return LogManager()


def get_logger(name: str) -> BaseLogger:
    """快捷获取日志记录器（非注入场景使用）"""
    return get_log_manager().get_logger(name)
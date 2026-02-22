"""日志模块 - 日志封装，支持 @inject 注入"""

from functools import lru_cache

from injector import inject, Inject
from services_common.logging import Logger as BaseLogger

class LogManager:
    """日志管理器 - 用于创建带名称的日志记录器
    
    此类可被注入到服务中，用于获取对应模块的日志记录器。
    
    Usage:
        class MyService:
            @inject
            def __init__(self, log_manager: LogManager):
                self.logger = log_manager.get_logger(__name__)
    """
    
    @inject
    def __init__(self) -> None:
        """初始化日志管理器"""
        self._loggers: dict[str, BaseLogger] = {}
    
    def get_logger(self, name: str) -> BaseLogger:
        """获取指定名称的日志记录器
        
        Args:
            name: 日志记录器名称
            
        Returns:
            Logger 实例
        """
        if name not in self._loggers:
            self._loggers[name] = BaseLogger(name)
        return self._loggers[name]


@lru_cache
def get_log_manager() -> LogManager:
    """获取日志管理器单例（用于非注入场景）
    
    Returns:
        LogManager 实例
    """
    return LogManager()


def get_logger(name: str) -> BaseLogger:
    """快捷获取日志记录器（非注入场景使用）
    
    Args:
        name: 日志记录器名称
        
    Returns:
        Logger 实例
    """
    return get_log_manager().get_logger(name)

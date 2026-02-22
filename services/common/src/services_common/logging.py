"""日志模块 - 基于 structlog 的结构化日志封装"""

import logging
import sys
from typing import Any, Optional

import structlog

from services_common.middleware.request_id import get_request_id


class RequestIDProcessor:
    """structlog processor - 自动将 request_id 添加到日志上下文"""

    def __call__(self, logger, method_name, event_dict):
        request_id = get_request_id()
        if request_id:
            event_dict["request_id"] = request_id
        return event_dict


# 配置 structlog
def configure_logging(log_level: int = logging.INFO) -> None:
    """配置 structlog 全局设置
    
    Args:
        log_level: 日志级别
    """
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )
    
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            RequestIDProcessor(),  # 自动添加 request_id
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


class Logger:
    """日志记录器封装类
    
    使用 structlog 提供结构化日志记录，支持标准 logging 接口和结构化日志。
    
    Usage:
        logger = Logger("my_module")
        logger.info("Starting service", service="account")
        logger.error("Failed to connect", exc_info=True)
        
        # 也可以使用标准 logging 方式
        logger.logger.info("Standard logging message")
    """
    
    def __init__(
        self,
        name: str,
        level: int = logging.INFO,
    ) -> None:
        """初始化日志记录器
        
        Args:
            name: 日志记录器名称
            level: 日志级别
        """
        # 确保全局配置已执行
        if not structlog.is_configured():
            configure_logging(level)
        
        self._logger = structlog.get_logger(name)
        self._name = name
        self._level = level
        
        # 同时保留标准 logging 记录器以兼容旧代码
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
    
    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:
        """记录调试日志"""
        self._logger.debug(message, *args, **kwargs)
    
    def info(self, message: str, *args: Any, **kwargs: Any) -> None:
        """记录信息日志"""
        self._logger.info(message, *args, **kwargs)
    
    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        """记录警告日志"""
        self._logger.warning(message, *args, **kwargs)
    
    def error(self, message: str, *args: Any, **kwargs: Any) -> None:
        """记录错误日志"""
        self._logger.error(message, *args, **kwargs)
    
    def critical(self, message: str, *args: Any, **kwargs: Any) -> None:
        """记录严重错误日志"""
        self._logger.critical(message, *args, **kwargs)
    
    def exception(self, message: str, *args: Any, **kwargs: Any) -> None:
        """记录异常日志（自动包含堆栈信息）"""
        self._logger.exception(message, *args, **kwargs)
    
    def log(self, level: int, message: str, *args: Any, **kwargs: Any) -> None:
        """通用日志方法"""
        self._logger.log(level, message, *args, **kwargs)
    
    def set_level(self, level: int) -> None:
        """设置日志级别"""
        self._level = level
        self.logger.setLevel(level)



def get_logger(name: str) -> Logger:
    """获取日志记录器快捷函数
    
    Args:
        name: 日志记录器名称
        
    Returns:
        Logger 实例
    """
    return Logger(name)

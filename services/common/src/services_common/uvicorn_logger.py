import logging
import sys
from typing import Any

from services_common.logging import get_logger
from services_common.middleware.request_id import get_request_id


class RequestIDProcessor:
    """structlog processor - 自动将 request_id 添加到日志上下文"""

    def __call__(self, logger, method_name, event_dict):
        request_id = get_request_id()
        if request_id:
            event_dict["request_id"] = request_id
        return event_dict


# 配置 uvicorn JSON 日志
class JsonFormatter(logging.Formatter):
    """JSON 格式化器，用于 uvicorn 访问日志"""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt or "iso"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # 添加请求信息
        if hasattr(record, "client"):
            log_data["client"] = record.client
        if hasattr(record, "method"):
            log_data["method"] = record.method
        if hasattr(record, "path"):
            log_data["path"] = record.path
        if hasattr(record, "status_code"):
            log_data["status_code"] = record.status_code
        if hasattr(record, "duration"):
            log_data["duration"] = record.duration

        import json
        return json.dumps(log_data)


def configure_uvicorn_logging():
    """配置 uvicorn 日志为 JSON 格式"""
    logger = get_logger(__name__)
    
    # 配置 root logger
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )

    # 配置 uvicorn access log
    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    uvicorn_access_logger.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    uvicorn_access_logger.addHandler(handler)
    uvicorn_access_logger.setLevel(logging.INFO)

    # 配置 uvicorn error log
    uvicorn_error_logger = logging.getLogger("uvicorn.error")
    uvicorn_error_logger.setLevel(logging.INFO)
    
    logger.info("Uvicorn logging configured", format="json")


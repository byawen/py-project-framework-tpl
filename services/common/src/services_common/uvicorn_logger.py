"""uvicorn 日志配置 - JSON 格式，控制台 + 文件同步输出"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from services_common.logging import get_logger, write_to_file, is_file_logging_enabled
from services_common._context import get_request_id


class _JsonFormatter(logging.Formatter):
    """将 logging.LogRecord 序列化为 JSON 字符串。"""

    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "time": self.formatTime(record, "%Y-%m-%d %H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        rid = get_request_id()
        if rid:
            data["request_id"] = rid
        for field in ("client", "method", "path", "status_code", "duration"):
            if hasattr(record, field):
                data[field] = getattr(record, field)
        if record.exc_info:
            data["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False)


class _FileHandler(logging.Handler):
    """将已格式化的日志写入文件队列（仅当 LOG_FILE=true 且队列就绪时生效）。"""

    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(_JsonFormatter())

    def emit(self, record: logging.LogRecord) -> None:
        if not is_file_logging_enabled():
            return
        try:
            write_to_file(self.format(record))
        except Exception:
            self.handleError(record)


# 全局共享的文件 handler（所有 uvicorn logger 复用同一实例）
_file_handler = _FileHandler()
_json_formatter = _JsonFormatter()


def _setup_logger(
    name: str,
    level: int = logging.INFO,
    propagate: bool = False,
) -> None:
    """统一配置单个 uvicorn logger：JSON 控制台 + 文件输出。"""
    lg = logging.getLogger(name)
    lg.handlers.clear()
    lg.setLevel(level)
    lg.propagate = propagate

    # 控制台 handler（JSON 格式）
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(_json_formatter)
    ch.setLevel(level)
    lg.addHandler(ch)

    # 文件 handler（动态检测是否就绪）
    lg.addHandler(_file_handler)


def configure_uvicorn_logging() -> None:
    """配置 uvicorn 所有 logger 为 JSON 格式，并同步写入文件（若 LOG_FILE=true）。

    - uvicorn.access : propagate=False，独立管理，避免重复输出到 root logger
    - uvicorn.error  : propagate=False，独立管理
    - uvicorn        : propagate=True，传播到 root logger（供三方库日志聚合）
    """
    _setup_logger("uvicorn.access", propagate=False)
    _setup_logger("uvicorn.error", propagate=False)
    # 主 uvicorn logger 只设级别，不清 handlers，让其自然传播到 root
    logging.getLogger("uvicorn").setLevel(logging.INFO)

    logger = get_logger(__name__)
    logger.info(
        "Uvicorn logging configured",
        format="json",
        file_enabled=is_file_logging_enabled(),
    )

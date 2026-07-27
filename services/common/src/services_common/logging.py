"""统一日志模块

设计原则：
  - 简单可靠：所有日志经过同一条路径，无传播链依赖
  - 延迟写入：FileWriterProcessor 在每次 emit 时检查队列是否就绪，
              无需关心初始化顺序
  - 开关独立：LOG_CONSOLE / LOG_FILE 分别控制，互不影响
  - 幂等配置：configure_logging 可多次调用，安全

环境变量：
  LOG_LEVEL   : DEBUG / INFO / WARNING / ERROR / CRITICAL（默认 INFO）
  LOG_CONSOLE : true / false（默认 true）
  LOG_FILE    : true / false（默认 false）
  LOG_DIR     : 日志根目录，LOG_FILE=true 时必填
  SERVICE_NAME: 日志文件名前缀（优先于 configure_logging 的 service_name 参数）
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import queue
import sys
from pathlib import Path
from typing import Any, Optional, Union

import structlog

# ---------------------------------------------------------------------------
# request_id 上下文（相对导入 _context，不经过 services_common/__init__.py）
# ---------------------------------------------------------------------------
from ._context import get_request_id

# ---------------------------------------------------------------------------
# 内部状态（模块级单例）
# ---------------------------------------------------------------------------

class _State:
    """模块级可变状态，封装在类里方便测试时替换。"""
    log_level: int = logging.INFO
    log_console: bool = True
    log_file: bool = False
    log_file_max_bytes: int = 100 * 1024 * 1024
    log_file_backup_count: int = 100
    file_queue: Optional[queue.Queue] = None
    queue_listener: Optional[logging.handlers.QueueListener] = None
    configured: bool = False  # 是否已调用过 configure_logging


_state = _State()


# ---------------------------------------------------------------------------
# 环境变量工具
# ---------------------------------------------------------------------------

def _parse_level(value: Union[int, str, None], default: int = logging.INFO) -> int:
    if value is None:
        raw = os.getenv("LOG_LEVEL", "INFO").upper()
    elif isinstance(value, int):
        return value
    else:
        raw = value.upper()
    return {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "WARN": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }.get(raw, default)


def _parse_bool(key: str, default: bool) -> bool:
    val = os.getenv(key, "").strip().lower()
    if not val:
        return default
    return val in ("true", "1", "yes")


def _resolve_log_dir(log_dir: Optional[str]) -> Optional[Path]:
    """解析日志目录：优先参数，其次环境变量 LOG_DIR。"""
    if log_dir is None:
        raw = os.getenv("LOG_DIR", "").strip()
    elif log_dir == "":
        return None
    else:
        raw = log_dir
    return Path(raw) if raw else None


# ---------------------------------------------------------------------------
# 文件写入器（后台线程）
# ---------------------------------------------------------------------------

def _build_log_file_path(base: Path, service_name: str) -> Path:
    """构建日志文件路径：不分日期目录，日期拼接在文件名中。"""
    base.mkdir(parents=True, exist_ok=True)
    # date_str = datetime.now().strftime("%Y-%m-%d")
    return base / f"{service_name}.log"


def _init_file_writer(log_dir: Path, service_name: str) -> None:
    """初始化后台文件写入线程（幂等）。"""
    if _state.file_queue is not None:
        return  # 已初始化

    log_file = _build_log_file_path(log_dir, service_name)
    fh = logging.handlers.RotatingFileHandler(
        filename=str(log_file),
        maxBytes=_state.log_file_max_bytes,
        backupCount=_state.log_file_backup_count,
        encoding="utf-8",
        delay=False,
    )
    fh.setFormatter(logging.Formatter("%(message)s"))

    q: queue.Queue = queue.Queue(maxsize=-1)
    listener = logging.handlers.QueueListener(q, fh, respect_handler_level=False)
    listener.start()

    _state.file_queue = q
    _state.queue_listener = listener


def write_to_file(message: str) -> None:
    """将已序列化的日志字符串写入文件队列（非阻塞）。供外部模块直接调用。"""
    if _state.file_queue is None:
        return
    _state.file_queue.put_nowait(
        logging.LogRecord(
            name="file", level=logging.INFO,
            pathname="", lineno=0,
            msg=message, args=(), exc_info=None,
        )
    )


def is_file_logging_enabled() -> bool:
    return _state.log_file and _state.file_queue is not None


# ---------------------------------------------------------------------------
# structlog processors
# ---------------------------------------------------------------------------

class _RequestIDProcessor:
    def __call__(self, logger, method, event_dict):
        rid = get_request_id()
        if rid:
            event_dict["request_id"] = rid
        return event_dict


class _JSONRenderer:
    """JSON 渲染，ensure_ascii=False 保留中文。"""
    def __call__(self, logger, method, event_dict):
        return json.dumps(event_dict, ensure_ascii=False, default=str)


class _FileWriterProcessor:
    """在 JSON 渲染后将字符串投入文件队列。

    每次 emit 时动态检查队列是否就绪，
    因此无论 logger 实例何时创建，只要队列已初始化就能写入文件。
    """
    def __call__(self, logger, method, event_dict):
        if isinstance(event_dict, str) and _state.file_queue is not None:
            write_to_file(event_dict)
        return event_dict


class _AddLoggerNameProcessor:
    """添加 logger 名称到 event_dict。"""
    def __call__(self, logger, method, event_dict):
        record = event_dict.get("_record")
        if record:
            event_dict["logger"] = record.name
        elif hasattr(logger, "name"):
            event_dict["logger"] = logger.name
        return event_dict


class _OperationProcessor:
    """统一补充 operation 字段，保证每条日志都有 operation。"""
    def __call__(self, logger, method, event_dict):
        if not event_dict.get("operation"):
            event = event_dict.get("event")
            if isinstance(event, str) and event.strip():
                event_dict["operation"] = event.strip()
            else:
                event_dict["operation"] = method.lower()
        return event_dict


class _LevelFilterProcessor:
    """根据 _state.log_level 过滤日志级别。"""
    _level_map = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "warn": logging.WARNING,
        "error": logging.ERROR,
        "critical": logging.CRITICAL,
    }

    def __call__(self, logger, method, event_dict):
        level = self._level_map.get(method.lower(), logging.INFO)
        if level < _state.log_level:
            raise structlog.DropEvent()
        return event_dict


class _NullWriter:
    """丢弃所有写入，供 PrintLoggerFactory 使用（实际输出由 _ConsoleWriterProcessor 处理）。"""
    def write(self, s): pass
    def flush(self): pass


class _ConsoleWriterProcessor:
    """将最终 JSON 字符串直接写入 stdout，保留中文原文。

    完全绕过 stdlib logging，避免 LogRecord 二次转义 unicode。
    """
    def __call__(self, logger, method, event_dict):
        if _state.log_console and isinstance(event_dict, str):
            print(event_dict, flush=True)
        return event_dict



def configure_logging(
    log_level: Union[int, str, None] = None,
    service_name: str = "service",
    log_dir: Optional[str] = "./logs",
    log_console: Optional[bool] = True,
    log_file: Optional[bool] = False,
    log_file_max_bytes: Optional[int] = 100 * 1024 * 1024,
    log_file_backup_count: Optional[int] = 100,
) -> None:
    """配置全局日志系统。可多次调用（幂等）。

    Args:
        log_level            : 日志级别，None 读环境变量 LOG_LEVEL
        service_name         : 日志文件名前缀（优先于环境变量 SERVICE_NAME）
        log_dir              : 日志根目录，None 读环境变量 LOG_DIR，"" 禁用文件日志
        log_console          : 是否输出控制台，None 读环境变量 LOG_CONSOLE（默认 true）
        log_file             : 是否写入文件，None 读环境变量 LOG_FILE（默认 false）
        log_file_max_bytes   : 单个日志文件最大字节数，None 读环境变量 LOG_FILE_MAX_BYTES（默认 100MB）
        log_file_backup_count: 最多保留的滚动备份数，None 读环境变量 LOG_FILE_BACKUP_COUNT（默认 100）
    """
    _state.log_level = _parse_level(log_level)
    _state.log_console = log_console
    _state.log_file = log_file
    _state.log_file_max_bytes = log_file_max_bytes
    _state.log_file_backup_count = log_file_backup_count

    # --- root logger（控制台输出走标准 logging）---
    root = logging.getLogger()
    root.setLevel(_state.log_level)
    # 清空旧 handlers，重建，避免 uvicorn/gunicorn 重置后重复
    root.handlers.clear()
    if _state.log_console:
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(logging.Formatter("%(message)s"))
        sh.setLevel(_state.log_level)
        # 确保 stdout 以 UTF-8 编码输出，防止中文被转义
        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8")
            except Exception:
                pass
        root.addHandler(sh)

    # --- 文件写入器 ---
    if _state.log_file:
        resolved = _resolve_log_dir(log_dir)
        if resolved is not None:
            svc = service_name
            try:
                _init_file_writer(resolved, svc)
            except Exception as exc:
                _state.log_file = False
                logging.getLogger(__name__).warning(
                    f"文件日志初始化失败，降级为控制台输出: {exc}"
                )
        else:
            _state.log_file = False

    # --- structlog 配置 ---
    # 使用 PrintLoggerFactory 直接写 stdout，完全绕过 stdlib logging，
    # 避免 LogRecord.getMessage() 对 unicode 做二次转义。
    # 文件写入由 _FileWriterProcessor 独立处理，不依赖 logger_factory。
    logger_factory_cls = getattr(structlog, "PrintLoggerFactory", None)
    logger_factory = (
        logger_factory_cls(file=_NullWriter())
        if logger_factory_cls is not None
        else structlog.stdlib.LoggerFactory()
    )

    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False, key="time"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            _RequestIDProcessor(),
            _AddLoggerNameProcessor(),
            _OperationProcessor(),
            _LevelFilterProcessor(),
            _JSONRenderer(),
            _FileWriterProcessor(),  # 始终挂载；队列未就绪时无操作
            _ConsoleWriterProcessor(),  # 直接写 stdout，保留中文
        ],
        context_class=dict,
        logger_factory=logger_factory,
        cache_logger_on_first_use=False,
    )
    _state.configured = True


# ---------------------------------------------------------------------------
# Logger 封装
# ---------------------------------------------------------------------------

class Logger:
    """日志记录器封装。

    Usage:
        logger = get_logger(__name__)
        logger.info("用户登录", user_id="u123", ip="1.2.3.4")
    """

    __slots__ = ("_sl", "_name", "logger")

    def __init__(self, name: str) -> None:
        # 如果尚未配置，先做一次仅控制台的基础配置
        if not _state.configured:
            configure_logging()
        self._sl = structlog.get_logger(name)
        self._name = name
        # 兼容旧代码直接使用 .logger 的场景
        self.logger = logging.getLogger(name)

    def debug(self, msg: str, *a: Any, **kw: Any) -> None:
        self._sl.debug(msg, *a, **kw)

    def info(self, msg: str, *a: Any, **kw: Any) -> None:
        self._sl.info(msg, *a, **kw)

    def warning(self, msg: str, *a: Any, **kw: Any) -> None:
        self._sl.warning(msg, *a, **kw)

    def error(self, msg: str, *a: Any, **kw: Any) -> None:
        self._sl.error(msg, *a, **kw)

    def critical(self, msg: str, *a: Any, **kw: Any) -> None:
        self._sl.critical(msg, *a, **kw)

    def exception(self, msg: str, *a: Any, **kw: Any) -> None:
        self._sl.exception(msg, *a, **kw)

    def log(self, level: int, msg: str, *a: Any, **kw: Any) -> None:
        self._sl.log(level, msg, *a, **kw)


def get_logger(name: str) -> Logger:
    """获取日志记录器（推荐入口）。"""
    return Logger(name)


# ---------------------------------------------------------------------------
# 关闭
# ---------------------------------------------------------------------------

def shutdown_file_logging() -> None:
    """优雅关闭文件日志，确保队列中所有日志写入磁盘后再退出。

    在 FastAPI lifespan shutdown 阶段调用。
    """
    if _state.queue_listener is not None:
        try:
            _state.queue_listener.stop()
        except Exception:
            pass

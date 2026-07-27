"""清理 UTF-16 孤立代理字符（surrogate）

JavaScript 客户端可能产生不配对的代理字符（如 \\uda4e），
Python str 可以持有它们，但 UTF-8 编码和 json.dumps 默认模式都不接受。
此模块提供递归清理函数，用于在写入数据库前净化数据。
"""

import re
from typing import Any

_SURROGATE_RE = re.compile(r"[\ud800-\udfff]")


def sanitize_surrogates(value: Any) -> Any:
    """递归清理值中的孤立代理字符

    - str: 移除代理字符
    - dict: 递归清理 key 和 value
    - list/tuple: 递归清理每个元素
    - 其他类型: 原样返回
    """
    if isinstance(value, str):
        return _SURROGATE_RE.sub("", value)
    if isinstance(value, dict):
        return {sanitize_surrogates(k): sanitize_surrogates(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_surrogates(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_surrogates(item) for item in value)
    return value
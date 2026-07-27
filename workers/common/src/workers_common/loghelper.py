"""日志辅助工具 - 公共敏感信息脱敏函数"""


def mask_sensitive(
    value: str | None,
    *,
    keep_prefix: int = 4,
    keep_suffix: int = 2,
) -> str:
    """脱敏处理敏感字段，保留前 keep_prefix 位和后 keep_suffix 位，中间以 *** 替换。

    Args:
        value: 待脱敏的字符串，可为 None
        keep_prefix: 保留前缀字符数，默认 4
        keep_suffix: 保留后缀字符数，默认 2

    Returns:
        脱敏后的字符串。None / 空字符串返回空串；长度不足时返回 "***"。

    Examples:
        >>> mask_sensitive("13812345678", keep_prefix=3, keep_suffix=2)
        '138***78'
        >>> mask_sensitive("abc", keep_prefix=4, keep_suffix=2)
        '***'
        >>> mask_sensitive(None)
        ''
    """
    if not value:
        return ""
    if len(value) <= keep_prefix + keep_suffix:
        return "***"
    return f"{value[:keep_prefix]}***{value[-keep_suffix:]}"


# 方便各 worker 按原有私有函数名直接替换 import
_mask_sensitive = mask_sensitive
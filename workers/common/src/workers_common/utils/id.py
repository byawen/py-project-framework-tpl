from uuid import uuid4


def generate_id() -> str:
    """生成 32 字符的无横线 UUID，用于业务 ID。

    旧数据中可能存在带 "-" 的 36 字符 UUID（如 xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx），
    新数据统一使用 32 字符的 hex 格式（如 xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx）。
    两种格式共存于数据库中，互不影响。
    """
    return uuid4().hex
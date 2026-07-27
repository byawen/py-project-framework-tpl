import json
from sqlalchemy import types


class DBJSONUnicode(types.TypeDecorator):
    """自定义 JSON 列：兼容 DB 原生 JSON 类型，同时支持中文 ensure_ascii=False 序列化

    impl = types.JSON 确保与 PostgreSQL JSON 列类型匹配（避免类型不匹配错误）。
    asyncpg 驱动使用自定义 json_serializer 处理序列化，
    此处 process_bind_param / process_result_value 直接透传 Python 对象即可。
    """
    impl = types.JSON
    cache_ok = True

    def process_bind_param(self, value, dialect):
        # 直接返回 Python 对象，由 asyncpg 的 json_serializer 处理序列化
        # json_serializer 在 DatabaseManager 初始化时配置为 ensure_ascii=False
        return value

    def process_result_value(self, value, dialect):
        # asyncpg 已经反序列化为 Python 对象，直接返回
        return value

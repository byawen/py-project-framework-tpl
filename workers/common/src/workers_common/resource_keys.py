DB_DEFAULT_KEY = "db:default"
REDIS_DEFAULT_KEY = "redis:default"


def db_key(name: str = "default") -> str:
    return f"db:{name}"


def redis_key(name: str = "default") -> str:
    return f"redis:{name}"


def resource_key(resource_type: str, name: str = "default") -> str:
    return f"resource:{resource_type}:{name}"
# 通用工具库

所有服务共享的通用工具、配置、数据库、Redis、异常和中间件。

## 使用方法

```python
from services_common.config import get_settings
from services_common.database import DatabaseManager
from services_common.redis import RedisManager
from services_common.exceptions import BaseException
```

## 开发指南

```bash
# 安装依赖
uv pip install -e ".[dev]"

# 运行测试
pytest
```

## 模块说明

- `config`: 配置管理
- `database`: 数据库连接管理
- `redis`: Redis 连接管理
- `exceptions`: 统一异常类
- `middleware`: 中间件（请求日志、请求ID、全局异常处理）
- `logging`: 结构化日志
- `response`: 统一响应格式
- `redis_cache`: Redis 缓存基类

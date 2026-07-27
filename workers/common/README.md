# Workers Common Library

所有 **worker**（后台任务进程）共享的基础工具库。

## 为什么独立于 `services_common`

`services/` 与 `workers/` 是两个独立的领域边界：

- `services_common`：面向 API/端口服务（FastAPI + uvicorn），包含 HTTP response、
  中间件、异常处理器、uvicorn JSON 日志等 **Web 专用能力**。
- `workers_common`：面向 Celery worker（无 API/端口），**不依赖** FastAPI/uvicorn，
  只保留 worker 运行所需的能力。

worker 代码 **禁止** 直接 import `services_common`，必须使用本库。

## 提供的能力

| 模块 | 说明 |
| --- | --- |
| `config` | `AppSettings` / `DatabaseSettings` / `RedisSettings` / `LLMSettings` / `Settings`（无 HOST/PORT/CORS 等 Web 字段） |
| `database` | `DatabaseManager` / `BaseModel`（异步 SQLAlchemy） |
| `redis` | `RedisManager` / `RedisWorkerLock`（单活 worker 锁） |
| `logging` | structlog 统一日志，`Logger` / `get_logger` / `configure_logging` / `shutdown_file_logging` |
| `exceptions` | 领域 / 应用层异常基类 |
| `shared_resources` | `SharedResources`（worker-in-one 共享 DB/Redis） |
| `resource_keys` | `DB_DEFAULT_KEY` / `REDIS_DEFAULT_KEY` / `db_key` / `redis_key` |
| `loghelper` | `mask_sensitive` 敏感信息脱敏 |
| `utils` | `generate_id` / `DBJSONUnicode` / `sanitize_surrogates` |
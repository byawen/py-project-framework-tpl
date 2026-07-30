# Worker 开发指南

> 面向新成员的端到端实战手册。读完本文你应当能够：独立创建一个新 Worker、理解它和 Service 的关系、写一个任务处理器、配置队列/重试/Beat 定时任务、跑通启动与日志，并了解它如何被部署（单进程聚合运行）。
>
> 本文与 `develop/ai-coding-worker-app.md` 互补：后者是"约束规范"（给 AI / Code Review，强调红线），本文是"上手教程"（给人，强调流程与为什么）。建议先读姊妹篇 `develop/service-development-guide.md` 第 5–12 节，因为 **Worker 复用 Service 的整套 DDD 分层与 DI 机制**，本文不重复讲基础，只讲 Worker 特有部分。
>
> 本仓库新成员能看到的只有两个包：`workers/pingpong-worker/`（模板/参考实现）与 `workers/common/`（共享库 `workers_common`）。本文所有示例均以通用场景展开，不涉及任何未提供给你的业务 Worker。

---

## 目录

1. [概念全景：Worker 是什么](#1-概念全景worker-是什么)
2. [Worker 与 Service 的关系](#2-worker-与-service-的关系)
3. [环境准备](#3-环境准备)
4. [技术栈：Celery + 自研 Broker 抽象](#4-技术栈celery--自研-broker-抽象)
5. [从一个新 Worker 开始](#5-从一个新-worker-开始0-到-1)
6. [目录结构](#6-目录结构)
7. [handlers：Worker 的"API 层"](#7-handlersworker-的-api-层)
8. [main.py：启动与 DI 装配](#8-mainpy启动与-di-装配)
9. [broker 抽象层](#9-broker-抽象层)
10. [app/：复用 DDD 四层 + 消息载体约定](#10-app复用-ddd-四层--消息载体约定)
11. [clients：Worker 调外部服务](#11-clientsworker-调外部服务)
12. [foundation：配置与日志](#12-foundation配置与日志)
13. [运行模式：Standalone vs Worker-in-One](#13-运行模式standalone-vs-worker-in-one)
14. [Worker-in-One 聚合运行原理](#14-worker-in-one-聚合运行原理)
15. [日志（重点：fork 后的日志修复）](#15-日志重点fork-后的日志修复)
16. [容错与重试：分层故障模型](#16-容错与重试分层故障模型)
17. [进阶：长任务的可恢复执行（checkpoint + outbox）](#17-进阶长任务的可恢复执行checkpoint--outbox)
18. [Beat 定时任务](#18-beat-定时任务)
19. [Producer 端：Service 如何投递任务](#19-producer-端service-如何投递任务)
20. [端到端任务流（通用示例）](#20-端到端任务流通用示例)
21. [新增一个任务（实战 walk-through）](#21-新增一个任务实战-walk-through)
22. [测试与 Lint](#22-测试与-lint)
23. [编码规范与提交前检查清单](#23-编码规范与提交前检查清单)
24. [从开发到部署](#24-从开发到部署)
25. [常见坑与排错](#25-常见坑与排错)
26. [附录：命令速查表](#26-附录命令速查表)

---

## 1. 概念全景：Worker 是什么

本仓库有两类可部署组件：

| 类型 | 目录 | 特征 |
|---|---|---|
| **Service** | `services/*-service/` | 有 HTTP 端口、FastAPI + uvicorn，对外提供 API |
| **Worker** | `workers/*-worker/` | **无 HTTP 端口**，消费消息队列（Celery over Redis），做异步/后台/长耗时任务 |

Worker 的运行单元长这样：

```
Producer(Service 用 send_task 投递)
        │  (Redis Broker, JSON)
        ▼
Celery 消费者进程 → 同步 handler(self, payload, **kwargs)
                        │ asyncio.run()  ← 桥接到异步
                        ▼
                   Application 层(Service/Query)  ← 复用 DDD
                        │ 注入
                   Domain 层(Entity/Repo接口)
                        ↑ 实现
                   Infrastructure 层(SQL Repo / Redis / 外部 client)
                        │
                   PostgreSQL / Redis / 外部服务
                        │
                   回调 Service（HTTP callback / outbox）
```

关键设计点（先记住）：

- **复用 Service 的 DDD 分层**：`app/{application, domain, infrastructure}` + `foundation` + `clients`。唯一区别是没有 `api/`，取而代之是 `handlers/`（消息入口层，等价于 Service 的 API 层）。
- **框架是 Celery over Redis**，但被包在自研 `BaseBroker` 抽象下，便于未来换 RabbitMQ/PubSub。
- **handler 是同步函数**（Celery prefork 进程要求），内部用 `asyncio.run()`（或常驻 event loop）桥接到 async application 层。
- **两种运行模式**：单 Worker standalone（`make dev-worker`）与聚合 Worker-in-One（`make worker-in-one`，把所有 Worker 跑进一个进程，生产用）。
- **长任务容错**：checkpoint 崩溃恢复 + Celery 重试 + 超时 + outbox 回调 + Beat 扫描，五层兜底（见第 16–17 节，按需启用）。
- **Worker 自有 DB**：只存执行元数据（`<prefix>_task_execution`、checkpoint、outbox、dead_letter），**不碰 Service 的业务表**。

---

## 2. Worker 与 Service 的关系

这是理解整个架构的关键。Worker 和 Service 是**并行部署、紧密协作**的两个单元：

```
┌─────────────────┐   send_task (Celery)    ┌─────────────────┐
│  某个 Service    │ ─────────────────────▶  │  某个 Worker    │
│  (HTTP API)     │                         │  (Celery 消费)  │
│                 │  ◀─── HTTP callback ──  │                 │
│  业务表         │  (进度 / 终态)           │  执行元数据表   │
│  <svc>_         │                         │  <prefix>_      │
└─────────────────┘                         └─────────────────┘
        │                                          │
        └──────── 共享 Redis (broker) ─────────────┘
```

| 维度 | Service | Worker |
|---|---|---|
| **协议** | HTTP (FastAPI) | Celery 消息（Redis broker） |
| **入口** | `app/api/` 端点 | `handlers/` 处理器 |
| **DB 表** | 业务表（`<svc>_*`） | 自有执行元数据（`<prefix>_task_execution`、checkpoint、outbox） |
| **Producer/Consumer** | 既是 producer（投任务）也是 HTTP 服务 | 既是 consumer（跑任务）也可能是 producer（子任务自分发） |
| **外部调用方向** | 被别人 HTTP 调 | HTTP 回调 Service；调外部服务做重活 |

**重要边界**：`workers/` **不得 import `services_common`**。Service 的共享库是 `services_common`，Worker 的共享库是 `workers_common`。两者平行，Worker 不依赖 Service 代码（需要 Service 能力时走 clients HTTP 调用）。

两个包的 `app/` 层**不共享** domain——Worker 有自己的 `app/domain`（为任务执行调优），通过 `clients/` HTTP 调 Service。

---

## 3. 环境准备

| 工具 | 版本 | 用途 |
|---|---|---|
| Python | ≥ 3.12 | 运行时 |
| uv | 最新 | 包管理 |
| Docker + Compose | 最新 | 本地起 PostgreSQL + **Redis**（Celery broker 必需） |
| Make | 任意 | 跑 Makefile |

```bash
git clone <repo-url> services-project && cd services-project
python3.12 -m venv .venv && source .venv/bin/activate
pip install uv
make install
make compose-up          # 起 PostgreSQL + Redis
```

> Worker 强依赖 Redis（Celery broker + result backend），本地开发必须 `make compose-up` 起 Redis。

uv workspace 机制同 Service：根 `pyproject.toml` 的 `[tool.uv.workspace].members` 包含所有 `workers/*` + `worker-in-one`，每个 Worker 通过 `workers-common = { workspace = true }` 依赖共享库。新增 Worker 时脚手架自动改根 `pyproject.toml`。

---

## 4. 技术栈：Celery + 自研 Broker 抽象

### 4.1 为什么是 Celery

- 成熟、生态广，prefork 模型适合 CPU/IO 混合任务。
- 自带 Beat 定时、重试、结果后端、队列路由。

依赖在 `workers/common/pyproject.toml` 与 `worker-in-one/pyproject.toml`：`"celery>=5.4.0"`。Broker URL 与 result backend 都是 Redis：

```
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_BROKER_RESULT_BACKEND=redis://localhost:6379/2
```

### 4.2 为何要再包一层 Broker 抽象

为了不把代码焊死在 Celery 上。`workers_common/broker/` 定义了 `BaseBroker` ABC：

```python
# workers/common/broker/base.py
class BaseBroker(ABC):
    @abstractmethod
    def start(self, extra_args: list[str] | None = None) -> None: ...
    @abstractmethod
    def stop(self) -> None: ...
    @abstractmethod
    def register_handler(self, topic: str, handler: Callable, **task_opts) -> None: ...
    @abstractmethod
    def send_task(self, topic: str, payload: dict[str, Any], **kwargs) -> Any: ...
```

`broker/factory.py` 的 `BROKER_REGISTRY` 做注册表：

```python
BROKER_REGISTRY: dict[str, str] = {
    "celery": "workers_common.broker.implementations.celery_broker.CeleryBroker",
    # "rabbitmq": "workers_common.broker.implementations.rabbitmq_broker.RabbitMQBroker",  # 待扩展
}
```

新增中间件（如 RabbitMQ）只需：在 `implementations/` 下加一个 `BaseBroker` 子类 → 在 `BROKER_REGISTRY` 注册一行。**符合开闭原则**，不改现有代码。每个 Worker 的 `broker/__init__.py` 还能用 `extend_broker_registry()` 追加本地实现。

---

## 5. 从一个新 Worker 开始

和 Service 一样，用脚本克隆 `workers/pingpong-worker`（模板）做有序字符串替换。

### 5.1 脚手架命令

```bash
make generate-worker WORKER=<kebab名> SHORT_PREFIX=<3-6位前缀>
# 例：
make generate-worker WORKER=notify SHORT_PREFIX=ntf
```

参数：
- `WORKER`：kebab-case，字母/数字/连字符，不能数字开头（如 `notify`）。
- `SHORT_PREFIX`：3–6 位字母/数字（如 `ntf`）。**会去 `workers/` 和 `services/` 双向查重**，避免和任何服务/Worker 撞前缀。

> Worker **不需要 `service_code` 和 `port`**（无 biz_code 池、无 HTTP 端口）。这是 Worker 与 Service 生成命令的主要差异。

### 5.2 生成后的完整流程

```bash
# 1. 生成
make generate-worker WORKER=notify SHORT_PREFIX=ntf

# 2. 进 venv 安装
source .venv/bin/activate
make install-worker WORKER=notify-worker

# 3. 起本地依赖（Redis 必需）
make compose-up

# 4. 配置 .env（从 env.example 复制，改 DATABASE_URL/REDIS_URL/BROKER_URL）
cp workers/notify-worker/env.example workers/notify-worker/.env

# 5. 跑迁移（Worker 自有 DB 表也要建）
make migrate-worker WORKER=notify-worker

# 6. 启动开发
make dev-worker WORKER=notify-worker
# → PYTHONPATH=src python -m notify_worker.main

# 7. 投递一个测试任务（用 Celery 或 Service 端 send_task）
```

### 5.4 （可选）接入 Worker-in-One

要让新 Worker 跑进聚合进程 `make worker-in-one`，需在 `worker-in-one/` 与 `deploy/` 做几处注册（根 pyproject、worker-in-one pyproject、foundation/config.py 多继承+访问器、workers.py 加载块、Dockerfile COPY+install、migrate-worker.sh）。

完整步骤与原理见 [第 14 节](#14-worker-in-one-聚合运行原理)（特别是 §14.8 接入清单与 §14.2 装配细节）。核心两步预览：

```python
# worker-in-one/src/worker_in_one/workers.py 的 workers_registry()
async def workers_registry(_settings: Settings, logger: Logger) -> tuple[list[WorkerSpec], Callable]:
    try:
        from xxx_worker.main import setup as xxx_worker_setup
        from xxx_worker.handlers import register_all_handlers as xxx_register
        worker_settings = _settings.get_xxx_worker_settings()
        cleaner = await xxx_worker_setup(worker_settings, logger, shared_resources=shared_resources)
        cleaner_list.append(cleaner)
        specs.append(
            WorkerSpec(
                name="xxx-worker",
                broker_type="celery",
                register_handlers=xxx_register,
                settings=worker_settings,
            )
        )
        logger.info("Loaded worker: xxx-worker")
    except Exception as e:
        logger.warning(f">>>>>>> Failed to load xxx-worker exception: {e}")
        logger.warning(f">>>>>>> Failed to load xxx-worker stack: {traceback.format_exc()}")
```

```python
# worker-in-one/src/worker_in_one/foundation/config.py 的 Settings 多继承 + 访问器
class Settings(WorkerInOneSettings, ..., NotifySettings):
    def get_notify_worker_settings(self):
        config_dict = vars(self).copy()
        config_dict.update({
            "MODEL": "worker-in-one",
            "APP_NAME": self.APP_NAME + "-notify",
            "REDIS_PREFIX": "ntf",
            # 映射公共 CELERY_* 到 NTF_CELERY_* 前缀字段
            "CELERY_TASK_ROUTES": self.NTF_CELERY_TASK_ROUTES,
            ...
        })
        return NotifySettings(**config_dict)
```

---

## 6. 目录结构

生成后的 Worker 骨架（以 `notify-worker` 为例）：

```
notify-worker/
├── .env / env.example
├── Makefile
├── README.md
├── alembic.ini               # version_table 用前缀
├── pyproject.toml            # 依赖 workers-common（workspace）
├── worker.metadata           # {worker_name, worker_prefix}
├── alembic/
│   ├── env.py
│   └── script.py.mako
├── tests/
└── src/
    └── notify_worker/        # 导入根（PYTHONPATH=src）
        ├── __init__.py
        ├── main.py           # run_worker() 入口 + setup() DI 装配
        ├── foundation/       # config / container / logging（无 biz_code、无 exception_handlers）
        ├── handlers/         # ★ Worker 的入口层（等价 Service 的 api/）
        │   ├── __init__.py   # 导出 register_all_handlers
        │   ├── registry.py   # topic → handler 注册表
        │   └── <任务>.py      # 一个任务一个 handler 文件
        ├── clients/          # 调 Service / 第三方（HTTP）
        ├── pkg/              # 工具
        └── app/              # DDD 四层（复用 Service 规范）
            ├── application/  # commands/queries/services/modules
            ├── domain/       # entities/vo/repositories/caches/exceptions
            └── infrastructure/  # persistence/caches/...
```

**与 Service 的结构差异**只有两处：

1. **没有 `app/api/`**，取而代之是顶层的 `handlers/`。
2. **`foundation/` 没有 `biz_code.py` / `exception_handlers.py`**（Worker 无 HTTP 响应，不需要统一响应 envelope 与 biz_code 透传；Worker 内部异常体系走 `workers_common`）。

`app/` 下的 `application/ domain/ infrastructure/` 与 Service 完全同构，遵循同样的分层、依赖方向、四种数据载体规则。详见姊妹篇 Service 指南第 5–12 节。

---

## 7. handlers：Worker 的"API 层"

`handlers/` 是消息入口层。`handlers/__init__.py` 的 docstring 说得很直白：

> 消息/任务处理器，是 Worker 的入口交互层，等价于 Service 的 API 层。

### 7.1 handler 约定

一个 handler 是一个**同步函数**（Celery prefork 进程要求），签名固定：

```python
def handle_xxx_task(
    self,                              # Celery bind=True 的 task 实例
    payload: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """同步入口，内部桥接异步逻辑"""
    raw = dict(payload) if payload else dict(kwargs)   # 兼容 kwargs 风格（推荐）与旧 args 风格
    logger.info("Received xxx task", payload=raw)
    try:
        result = asyncio.run(_async_handle_xxx(raw))   # 桥接到 async
        return result
    except Exception as e:
        logger.error("xxx task failed", error=str(e), payload=raw)
        raise                       # 抛出 → 触发 Celery 重试
```

要点：
- **同步签名**，`self` 是 Celery task（`bind=True`），可用 `self.retry()` 等。
- **入参兼容两种**：`payload`（旧 args 风格，可选）与 `**kwargs`（推荐，对齐 `services_common.task_publisher` 协议）。合并成 `raw = dict(payload) if payload else dict(kwargs)`。
- **桥接 async**：轻量任务用 `asyncio.run(_async_xxx(raw))`；长任务/常驻循环用常驻 event loop（见 7.3）。
- **返回 dict**：仅在**队列边界**（payload-in / result-out）允许裸 dict；进入 application 层前必须转成 pydantic 模型。
- **抛出异常 = 触发重试**；返回正常 = 任务成功。

> 模板 `handlers/pp_demo.py` 里的 `handle_pingpong_task` 就是这个模式的完整范例，可直接对照。

### 7.2 调 application 层

```python
# handlers/pp_demo.py（模板）
async def _async_handle_pingpong(payload: dict[str, Any]) -> dict[str, Any]:
    injector = get_injector()                       # 全局 injector（启动时 set）
    from pingpong_worker.app.application.services.pp_service import PPService
    pp_service = injector.get(PPService)            # 取 application service
    message = payload.get("message", "ping")
    data = payload.get("data", "pong")
    ping, pong = await pp_service.ping_and_pong(message, data)
    return {"ping_id": ping.ping_id, "pong_id": pong.pong_id,
            "message": ping.message, "data": pong.data}
```

handler 本身**不写业务逻辑**，只做：解析 payload → 取 injector → 调 application → 组装结果。业务逻辑在 application/domain，与 Service 一致。

### 7.3 同步→异步的两种桥接

- **`asyncio.run()`**（模板默认）：简单任务够用，每次新建 event loop。注意 `asyncpg` 连接池会绑定到 loop，loop 关闭后连接失效——简单任务无所谓，长任务要小心。
- **常驻 event loop**（后台线程跑一个持久 loop）：复杂/长任务用这种方式，避免 `asyncpg` 池因 loop 反复创建/关闭而失效。需要一个模块级 helper（模板未内置，长任务 Worker 自行实现，典型形如 `run_async(coro)` 把协程提交到常驻 loop）。

### 7.4 registry：注册处理器

### 7.4 registry：注册处理器 + topic/队列命名

```python
# handlers/registry.py
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from workers_common.broker.base import BaseBroker

# topic 用模块级常量声明，config 路由与 registry 共用、避免拼写漂移
SEND_EMAIL_TOPIC = "notify_worker.send_email"          # 两段 {pkg}.{task}
DAILY_CLEANUP_TOPIC = "notify_worker.daily_cleanup"    # Beat 型也是两段


def register_all_handlers(broker: "BaseBroker") -> None:
    from notify_worker.handlers.send_email_handler import handle_send_email
    broker.register_handler(SEND_EMAIL_TOPIC, handle_send_email)

    # 新增 handler 在此注册：
    # from notify_worker.handlers.your_handler import handle_your_task
    # broker.register_handler(YOUR_TASK_TOPIC, handle_your_task)
```

**topic 命名格式（两段点分 snake，强制）**：`{pkg}.{task}`

- 第 1 段 `{pkg}` = worker 包名（`notify_worker`、`content_ops_worker`）。
- 第 2 段 `{task}` = 任务名 snake_case（`send_email`、`process_video`、`daily_cleanup`）。
- **两段，不带 `tasks` 固定段**。消费型和 Beat 型用同一格式（Beat 靠 `CELERY_BEAT_SCHEDULE` 区分）。
- 全小写，词用 `_`，段用 `.`。`notify_worker.send_email` ✅，不是 `notify_worker.send_email`/`sendEmail`/`send-email`。
- **用模块级常量声明 topic**（`SEND_EMAIL_TOPIC`），registry 与 producer 共用，杜绝拼写漂移。投递方 `send_task(topic)` 与注册字符串必须逐字一致。


**队列命名格式（三段点分 snake，强制）**：`{pkg}.{domain}.{subdomain}`

在 `foundation/config.py` 的 `CELERY_TASK_ROUTES` 里把每个 topic 路由到三段队列名：

```python
NTF_CELERY_TASK_ROUTES: dict = {
    "notify_worker.send_email":    {"queue": "notify_worker.email.send"},
    "notify_worker.send_sms":      {"queue": "notify_worker.sms.send"},
    "notify_worker.daily_cleanup": {"queue": "notify_worker.maintenance.cleanup"},
}
```

- 三段：`{pkg}`.{业务域}.{子域/动作}，全小写 snake，段用 `.`。`content_ops_worker.video.processing` ✅。
- 按业务域细分队列，让聚合 broker 能按队列 fork 隔离（慢队列不饿死快队列，见 §14.4）。
- 多个 topic 可共用一个队列（如多个 Beat 扫描任务共用 `content_ops_worker.callback_notify`）。
- `CELERY_TASK_QUEUES` 留空时，聚合 broker 从 routes 的 queue 值自动派生队列列表。

新增任务的三步：① 在 `handlers/` 下建文件写 handler；② 在 `registry.py` 加一行 `register_handler(TOPIC常量, handler)`；③ 在 `config.py` 的 `CELERY_TASK_ROUTES` 配 topic→三段 queue 路由。

---

## 8. main.py：启动与 DI 装配

每个 Worker 的 `main.py` 暴露两个东西：`setup()`（DI 装配，给聚合器调用）与 `run_worker()`（standalone 启动）。

### 8.1 `setup()` — 与 Service 的 `setup()` 同构

```python
# workers/pingpong-worker/src/pingpong_worker/main.py（简化）
async def setup(_settings, logger, shared_resources=None):
    # DB / Redis（Worker-in-One 模式复用 shared_resources）
    _db_manager = ... or DatabaseManager(database_url=_settings.DATABASE_URL, ...)
    _redis_manager = ... or RedisManager(redis_url=_settings.REDIS_URL, ...)

    class BuiltinModule(Module):
        def configure(self, binder):
            binder.bind(Settings, to=lambda: _settings, scope=None)
            binder.bind(RedisManager, to=lambda: _redis_manager, scope=None)
            binder.bind(DatabaseManager, to=lambda: _db_manager, scope=None)
            binder.bind(AsyncEngine, to=lambda: _db_manager.engine, scope=None)
            binder.bind(AsyncSession, to=lambda: _db_manager.session_maker, scope=None)
            binder.bind(LogManager, to=LogManager, scope=None)

    _injector = Injector([BuiltinModule, ClientsModule, DomainModule,
                          ApplicationModule, InfrastructureModule])
    set_injector(_injector)
    return cleaner   # 关闭资源
```

与 Service 的 `setup()` 几乎一致：同样的 5 个 Module、同样的 `BuiltinModule` 基础单例、同样的 `shared_resources` 共享机制。区别是不接收 `_app`/`api_prefix`（无 FastAPI app）。

### 8.2 `run_worker()` — standalone 启动

```python
def run_worker():
    _settings = get_settings()

    # 1. 配置日志
    configure_logging(service_name=_settings.APP_NAME, log_dir=..., ...)

    logger = get_logger(__name__)
    logger.info("Starting pingpong Worker...")

    # 2. 装配 DI（asyncio.run 跑 setup）
    asyncio.run(setup(_settings, logger))   # 注意：standalone 这里跑一次 setup

    # 3. 把 worker 专有前缀字段覆盖到公共 CELERY_* 字段
    _settings.CELERY_TASK_DEFAULT_QUEUE = _settings.PIPO_CELERY_TASK_DEFAULT_QUEUE
    _settings.CELERY_TASK_ROUTES = _settings.PIPO_CELERY_TASK_ROUTES
    _settings.CELERY_TASK_QUEUES = _settings.PIPO_CELERY_TASK_QUEUES

    # 4. 创建 BrokerManager 并启动消费
    from workers_common.broker import BrokerManager
    manager = BrokerManager()
    manager.register("celery", _settings)
    manager.start_all()    # → CeleryBroker.start() → app.worker_main(...)
```

**关键约定**：每个 Worker 在 `foundation/config.py` 里用**自己前缀的字段**（`PIPO_CELERY_TASK_ROUTES`、`NTF_CELERY_TASK_ROUTES`…）声明队列路由，启动时把这些前缀字段**赋值覆盖**到共享的 `CELERY_*` 字段上，再构造 `BrokerManager`。这样多 Worker 聚合时各自的路由不会互相污染（聚合器会合并，见第 14 节）。

`make dev-worker WORKER=xxx` 实际执行 `PYTHONPATH=src python -m <pkg>.main`，即调 `run_worker()`。

---

## 9. broker 抽象层

`workers_common/broker/` 的组成：

```
workers_common/broker/
├── base.py                 # BaseBroker ABC
├── factory.py              # BROKER_REGISTRY + create_broker()
├── manager.py              # BrokerManager（多 broker 统一管理）
└── implementations/
    └── celery_broker.py    # CeleryBroker（当前唯一实现）
```

### 9.1 BrokerManager

```python
manager = BrokerManager()
manager.register("celery", _settings)   # 按 broker_type 注册
manager.start_all()                      # 启动所有 broker
```

支持多 broker 类型并存（虽然当前只有 celery）。聚合模式 `Worker-in-One` 用更高级的 `BrokerRunner`/`CeleryAggregateBroker`（见第 14 节）。

### 9.2 扩展新中间件（开闭原则）

要加 RabbitMQ：

1. `workers_common/broker/implementations/rabbitmq_broker.py` 写 `RabbitMQBroker(BaseBroker)`，实现 `start/stop/register_handler/send_task`。
2. `factory.py` 的 `BROKER_REGISTRY` 加一行 `"rabbitmq": "workers_common.broker.implementations.rabbitmq_broker.RabbitMQBroker"`。
3. 在 Worker 的 `config.py` 配 `RABBITMQ_URL` 等。
4. `manager.register("rabbitmq", _settings)`。

**不改任何现有 handler 代码**——这就是抽象层的价值。

---

## 10. app/：复用 DDD 四层 + 消息载体约定

`app/` 下三层与 Service 完全同构，规则照搬姊妹篇：

- **依赖方向**：`application → domain ← infrastructure`，单向。domain 无框架依赖。
- **四种数据载体**：DTO（Worker 一般不用，无 HTTP）、Entity（domain）、ORM Model（infrastructure 内）、Client Schema（clients）。
- **Repository 接口在 domain，实现在 infrastructure**，`modules.py` 绑定。
- **CQRS**：写操作 `application/commands/`，读操作 `application/queries/`，跨聚合编排 `application/services/`。
- **DI via injector**：每个层一个 `modules.py`，`main.py` 装配 5 个 Module，`get_injector()` 暴露。

### Worker 特有的消息载体约定

- **队列边界允许裸 dict**：Celery payload（`send_task(topic, kwargs={...})`）和 handler 返回值可以是 dict——这是 Celery 的序列化协议要求。
- **进 application 前必须转 pydantic**：handler 里 `raw = dict(payload)` 后，应在调 application 前 `model = SomeInputModel(**raw)`，application 层只见 model，不见裸 dict。

```python
# 推荐：handler 里转模型
async def _async_handle(raw: dict):
    req = SomeTaskRequest(**raw)        # pydantic，校验 + 类型
    injector = get_injector()
    service = injector.get(SomeService)
    result = await service.run(req)
    return result.model_dump()          # 返回边界可裸 dict
```

### Worker 的 Repository 用途不同

Service 的 Repository 读写业务表；Worker 的 Repository 读写**执行元数据**：

- `<prefix>_task_execution`：任务执行状态/结果（先落盘，保证终态可恢复）
- `<prefix>_checkpoint`（可选）：长任务断点（见第 17 节）
- `callback_outbox`（可选）：待回调 Service 的消息（见第 16 节 Layer 4）
- `dead_letter`（可选）：重试耗尽的死信

命名同样带前缀（如 `ntf_task_execution`、`ntf_checkpoint`），多 Worker 共用库不撞表。

> 模板默认只带 pingpong 的演示表；`task_execution`/checkpoint/outbox 这些执行元数据表是长任务 Worker 按需用 alembic 自建的（见第 17 节）。

---

## 11. clients：Worker 调外部服务

Worker 的 `clients/` 与 Service 同构（五件套：interface / schemas / local_api / remote_api / api_proxy），用途是调 Service 与第三方服务。典型 clients 目录布局（以一个通用 Worker 为例）：

```
clients/
├── modules.py               # ClientsModule 绑定
├── some_service/            # 调某个内部 Service（回调 / 拉数据）
│   ├── interface.py         # SomeServiceClient(ABC)
│   ├── schemas.py
│   ├── remote_api.py        # httpx 实现（standalone）
│   ├── local_api.py         # 进程内实现（worker-in-one）
│   └── api_proxy.py         # 按 settings.MODEL 切
└── third_party_xx/          # 调第三方（只需 remote_api）
    ├── interface.py
    ├── schemas.py
    └── remote_api.py
```

约定与 Service 的 clients 完全一致（详见姊妹篇第 13 节）：

- ✅ 用 `httpx.AsyncClient`，带 `timeout`。
- ✅ 返回 pydantic Client Schema，不返回裸 dict。
- ✅ local/remote 由 `settings.MODEL` 切换（`worker-in-one` 模式走 local，直连 injector 取姊妹单元的 service；standalone 走 remote HTTP）。
- ✅ 在 `clients/modules.py` 绑定到 injector。
- ❌ `app/` 与 `handlers/` 里不直接 `import httpx`。

> 注意：Worker 的 `settings.MODEL` 取值是 `"standalone"` vs `"worker-in-one"`（不是 `"all-in-one"`）。`api_proxy.py` 里判断条件要对应。

模板 `clients/other_service/` 与 `clients/github/` 已经给了完整范例（一个内部服务五件套 + 一个第三方简化版），照抄结构即可。

---

## 12. foundation：配置与日志

### 12.1 config.py

```python
# workers/pingpong-worker/src/pingpong_worker/foundation/config.py
from workers_common import AppSettings, DatabaseSettings, RedisSettings, WorkersSettings
# ⚠️ 严禁 import services_common，Worker 边界红线

class Settings(AppSettings, DatabaseSettings, RedisSettings, WorkersSettings):
    """继承公共配置 + Worker 专有 Broker 配置"""

    model_config = SettingsConfigDict(env_file=".env", extra="allow", ...)

    # ── Broker 专有配置（用 worker 前缀，register 时覆盖 CELERY_*）──
    # topic 两段 {pkg}.{task}；queue 三段 {pkg}.{domain}.{sub}（见 §7.4）
    PIPO_CELERY_TASK_DEFAULT_QUEUE: str = "pingpong_worker.demo.pingpong"
    PIPO_CELERY_TASK_ROUTES: dict = {
        "pingpong_worker.pingpong": {"queue": "pingpong_worker.demo.pingpong"},
    }
    PIPO_CELERY_TASK_QUEUES: str = "pingpong_worker.demo.pingpong"

    # 任务超时（比默认更短）
    CELERY_TASK_TIME_LIMIT: int = 300
    CELERY_TASK_SOFT_TIME_LIMIT: int = 270

    REDIS_PREFIX: str = "pipo"
    OTHER_SERVICE_URL: str = "http://localhost:8001"

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

**与 Service config 的差异**：

1. 继承的是 `workers_common`（不是 `services_common`）的 Mixin，且多了 `WorkersSettings`（提供全部 `CELERY_*` 默认值）。
2. 用**前缀字段**（`PIPO_CELERY_*` / `NTF_CELERY_*`）声明队列路由，启动时覆盖到公共 `CELERY_*` 字段。
3. 无 `biz_code`。

`WorkersSettings`（在 `workers_common/config.py`）提供的默认字段：`CELERY_BROKER_URL`、`CELERY_BROKER_RESULT_BACKEND`、`CELERY_WORKER_CONCURRENCY`、`CELERY_TASK_SERIALIZER`、`CELERY_TIMEZONE`、`CELERY_TASK_TIME_LIMIT`、`CELERY_TASK_SOFT_TIME_LIMIT`、`CELERY_ACKS_LATE`、`CELERY_WORKER_MAX_TASKS_PER_CHILD`、`CELERY_BEAT_ENABLE`、`CELERY_BEAT_SCHEDULE`、prefetch、retry 等。

### 12.2 logging.py

薄封装 `workers_common.logging`，提供 `LogManager`（可注入）和 `get_logger()`。详见 [第 15 节](#15-日志重点fork-后的日志修复)。

---

## 13. 运行模式：Standalone vs Worker-in-One

| 模式 | 启动 | 特征 | 何时用 |
|---|---|---|---|
| **Standalone** | `make dev-worker WORKER=xxx` | 单 Worker 独立进程，自建 DB/Redis 连接，单 `BrokerManager`+`CeleryBroker` | 单 Worker 开发、调试 |
| **Worker-in-One** | `make worker-in-one` | 所有 Worker 跑进一个进程，**每队列 fork 子进程**，共享 DB/Redis，合并 Beat | 联调、生产部署 |

### 13.1 Worker-in-One 是什么

`worker-in-one/` 是独立包（workspace 成员），把**所有 Worker** 装进**一个 Celery 消费进程**：

- 一个主进程 + **每队列 fork 一个子进程**（独立并发槽、独立连接，慢队列不饿死快队列）。
- 共享一套 DB/Redis 连接池（`WORKER_IN_ONE_SHARE_DB/REDIS`）。
- 所有 Worker 的 handler 注册进**一个共享 Celery app**，路由/队列/Beat 合并。
- 单 Beat 实例（只第一个队列子进程带 `--beat`），避免多节点重复触发。

```
            ┌────────────────── worker-in-one 主进程 ──────────────────┐
            │  configure_logging → setup(workers_registry)             │
            │  → BrokerRunner.build → runner.run()                      │
            │  共享 SharedResources (DB/Redis)                           │
            └──────┬───────────────┬───────────────┬────────────────────┘
                   │ fork           │ fork           │ fork
            ┌──────▼──────┐  ┌──────▼──────┐  ┌─────▼───────┐
            │ 队列A 子进程 │  │ 队列B 子进程 │  │ 队列C(+Beat)│
            │ concurrency │  │ concurrency │  │ concurrency │
            │  =N         │  │  =M         │  │  =K         │
            └─────────────┘  └─────────────┘  └─────────────┘
            （每子进程内 Celery prefork pool 再 fork pool worker）
```

### 13.2 双 broker 抽象对偶

| | 单 Worker（standalone） | 聚合（worker-in-one） |
|---|---|---|
| 所在包 | `workers_common.broker` | `worker_in_one.broker` |
| 管理器 | `BrokerManager` | `BrokerRunner` |
| broker 类 | `CeleryBroker`（单 worker 的 handlers） | `CeleryAggregateBroker`（合并多 worker） |
| 桥梁 | — | `_CeleryRegisterAdapter` 把聚合 app 适配成"类 BaseBroker"，让 worker 的 `register_all_handlers(broker)` 无需改动 |

无论哪种模式，worker 自己的 `register_all_handlers(broker)` 只调 `broker.register_handler(topic, handler)`，不感知上层是单 broker 还是聚合 broker。

### 13.3 切换机制

- `Settings.MODEL`：`"standalone"` vs `"worker-in-one"`。clients 的 `api_proxy.py` 据此选 local/remote。
- `shared_resources`：`setup()` 收到时复用共享 `DatabaseManager`/`RedisManager`（`owns_db_manager`/`owns_redis_manager` 决定关闭权）。
- **共享 vs 隔离**：Redis 默认共享（`WORKER_IN_ONE_SHARE_REDIS=True`）；DB 默认共享注册，但部分 worker 可强制自建（如 content-ops 有独立执行元数据表，需要 schema 隔离）——在其 setup 里忽略 shared DB 即可。

### 13.4 为什么生产用聚合而不是多 Worker 各自起

- 减少进程数与连接数（共享 DB/Redis 池）。
- 统一 Beat 调度（单实例，避免重复触发）。
- 统一日志、监控、部署。
- 每队列仍 fork 独立子进程做隔离，慢队列不饿死快队列（见第 14 节）。

---

## 14. Worker-in-One 聚合运行原理

生产入口 `worker-in-one/src/worker_in_one/main.py::run_worker()`（Dockerfile `CMD`）。配置类在 `worker-in-one/src/worker_in_one/foundation/config.py`（注意是 `foundation/` 下）。

### 14.1 `run_worker()` 完整流程

1. `get_settings()` → `configure_logging(...)`（最先初始化日志，之后所有日志落盘）。
2. `asyncio.run(setup(settings, logger))` → `workers_registry()` 返回 `(specs, cleaner)`。
3. `BrokerRunner(settings, logger).build(specs)`：按 `broker_type` 分组建聚合 broker。
4. 注册 SIGINT/SIGTERM 信号处理 `_shutdown`：`runner.stop()` → `asyncio.run(cleaner())` → `shutdown_file_logging()` → `sys.exit(0)`。
5. `runner.run()`：前台 Celery broker 阻塞主线程（`requires_main_thread=True`），其余 broker 放 daemon 线程。

> 没有 FastAPI lifespan；退出清理靠信号处理。`cleaner` 会调各 worker 的 cleaner + `SharedResources.close_all()` 倒序关共享资源。

### 14.2 `workers_registry()` 装配细节

```
1. 建 SharedResources
2. if WORKER_IN_ONE_SHARE_DB:  register("db:default", DatabaseManager(...), closer=close)
   if WORKER_IN_ONE_SHARE_REDIS: register("redis:default", RedisManager(...), closer=close)
3. 遍历每个 worker:
     import <worker>.main.setup + <worker>.handlers.register_all_handlers
     worker_settings = _settings.get_<worker>_settings()    # 派生子 settings
     cleaner = await <worker>_setup(settings, logger, shared_resources=shared_resources)
     specs.append(WorkerSpec(name, broker_type="celery", register_handlers, settings))
4. return specs, cleaner
```

- 共享与否由 `WORKER_IN_ONE_SHARE_DB/REDIS`（默认 True）控制；False 时不注册，各 worker 自建。
- **当前注册的 worker**：`pingpong-worker`（已注册，失败只 warning）、`content-ops-worker`（已注册，失败 warning）、`data-collector-worker`（**必需**，失败 `raise RuntimeError` 终止启动）。
- 每个 worker 的 `setup` 接收 `shared_resources`，内部按 `owns_*` 决定复用共享还是自建（content-ops 始终自建 DB 做 schema 隔离）。
- `WorkerSpec` 是 dataclass：`name`、`broker_type`、`register_handlers`、`settings`。

### 14.3 `BrokerRunner` 与 `CeleryAggregateBroker`

- **`build(specs)`**：按 `spec.broker_type` 分组（当前全是 `"celery"`），每组 `create_aggregate_broker(type, settings)` 建一个 `CeleryAggregateBroker`，对每个 spec 调 `broker.register_worker(spec)`。
- **`run()`**：`requires_main_thread=True` 的 broker（Celery）放主线程前台 `.start()` 阻塞；其余放 `daemon=True` 线程。无前台 broker 时主线程 join 后台线程。
- **`register_worker(spec)`** 做四件事（合并到一个共享 Celery app）：
  1. 用 `_CeleryRegisterAdapter(self.app)` 适配，`spec.register_handlers(adapter)` 触发 `app.task(name=topic, bind=True)(handler)` 注册所有 handler。
  2. **合并 task_routes**：`merged = dict(app.conf.task_routes or {}); merged.update(worker的routes)`（worker 内 `current_app.send_task` 依赖路由投递到正确队列）。
  3. **收集队列**：优先 `CELERY_TASK_QUEUES`（逗号分隔），否则从 `CELERY_TASK_ROUTES` 的 `.queue` 派生；`CELERY_TASK_DEFAULT_QUEUE` 也进队列列表。全部去重。
  4. **收集 Beat**：`CELERY_BEAT_ENABLE=True` 且 `CELERY_BEAT_SCHEDULE` 非空时，`self._beat_schedule.update(schedule)`（多 worker 合并到一个 dict）。

### 14.4 每队列 fork 子进程（关键设计）

`CeleryAggregateBroker.start()` 为**每个队列** fork 一个子进程跑 `app.worker_main(["worker", "--queues=<单队列>", "--concurrency=N", "--hostname=...", ...])`。

**三层进程模型**：
```
worker-in-one 主进程 (main.py: setup/注册/信号)
  └─ fork × N（每队列一个子进程，_run_worker，第一层 fork，reinit 日志）
       └─ Celery prefork pool 再 fork × concurrency（pool worker，第二层 fork，worker_process_init 信号 reinit 日志）
```

**为什么 fork 而非多线程**：kombu 的 Redis transport 不是线程安全的（`_channels set` / `poll()`），多个 WorkController 线程共享连接池会触发 "concurrent poll() invocation"。fork 后每个子进程有独立 kombu hub 和连接池，彻底隔离。

**每队列并发**：`_parse_queue_concurrency()` 解析 `CELERY_QUEUE_CONCURRENCY` JSON（`{queue: concurrency}`），未列出的队列回退 `CELERY_WORKER_CONCURRENCY`：

```bash
CELERY_QUEUE_CONCURRENCY={"content_ops_worker.scene_task":2,"content_ops_worker.video.processing":3,"data_collect_fast":4,"data_collect_slow":3}
```

**Beat**：`use_beat = bool(self._beat_schedule)`；启用时只有**第一个**队列子进程带 `--beat`（`if (use_beat and i == 0)`）+ `--schedule=<filename>`（命令行优先级高于 app.conf，并 `os.makedirs` 父目录因 Celery `shelve.open` 不自动建目录）。hostname = `{app_name}@{queue.replace('.', '-')}`。

**OOM 守卫**（在 `app.conf.update(...)` 里，不在 CLI argv）：`worker_max_tasks_per_child`（默认 50）、`worker_max_memory_per_child`（默认 2_000_000 KB）、`task_reject_on_worker_lost=True`、`task_acks_late=True`、`worker_prefetch_multiplier`（默认 1）。

### 14.5 `resolve_schedule`：Beat schedule dict → Celery 对象

`workers_common.broker.resolve_schedule(schedule)`（单 worker 与聚合 broker 共用）把纯数据描述转 Celery 调度对象：

```python
{"crontab": {"minute": 0, "hour": 4}}   → celery.schedules.crontab(minute=0, hour=4)
{"timedelta": {"minutes": 5}}           → datetime.timedelta(minutes=5)
60 (int/float)                           → 原样（Celery 视为 interval seconds）
```

聚合 broker 在 `start()` 里遍历合并后的 `_beat_schedule`，`resolved[name] = {**entry, "schedule": resolve_schedule(entry["schedule"])}`，再 `app.conf.beat_schedule = resolved`。所以你在 worker 的 `Settings` 里用 dict 形式写 schedule 即可，无需自己构造 crontab/timedelta 对象。

### 14.6 真实路由与 Beat 示例（content-ops-worker）

content-ops 的配置（`{PREFIX}_CELERY_TASK_ROUTES` + `{PREFIX}_CELERY_BEAT_SCHEDULE`）是聚合 broker 合并的数据源：

```python
COPSW_CELERY_TASK_DEFAULT_QUEUE = "content_ops_worker.video.processing"
COPSW_CELERY_TASK_ROUTES = {
    "content_ops_worker.process_video":       {"queue": "content_ops_worker.video.processing"},
    "content_ops_worker.process_intelligence":{"queue": "content_ops_worker.intelligence"},
    "content_ops_worker.process_scene_task":  {"queue": "content_ops_worker.scene_task"},
    "content_ops_worker.callback_notify":     {"queue": "content_ops_worker.callback_notify"},
    "content_ops_worker.outbox_scan":         {"queue": "content_ops_worker.callback_notify"},
    "content_ops_worker.task_exec_cleanup":   {"queue": "content_ops_worker.callback_notify"},
}
COPSW_CELERY_TASK_QUEUES = ""   # 留空 → 聚合 broker 从 routes 派生队列

COPSW_CELERY_BEAT_ENABLE = True
COPSW_BEAT_SCHEDULE = {
    "outbox-scan-every-5min":     {"task": "content_ops_worker.outbox_scan",       "schedule": {"timedelta": {"minutes": 5}}},
    "task-exec-cleanup-daily-4am":{"task": "content_ops_worker.task_exec_cleanup","schedule": {"crontab": {"minute": 0, "hour": 4}}},
}
```

聚合后：4 个队列各 fork 一个子进程（`scene_task`/`video.processing`/`intelligence`/`callback_notify`），`callback_notify` 队列的子进程带 `--beat`，两条 Beat schedule 合并进共享 app。

### 14.7 两层 fork 的日志 reinit 与 env 变量

fork 不复制线程，父进程的 `QueueListener` 线程在子进程不存在，但 `_state.file_queue` 内存复制后非 None——日志会被投入队列却无人消费、永远不落盘。两层 fork 都要 `reinit_file_logging`：

- **第一层 fork**（队列子进程 `_run_worker`）：调 `reinit_file_logging(service_name="{APP_NAME}-{queue}", ...)`，日志文件名变 `{APP_NAME}-{queue}.log`。
- **第二层 fork**（Celery prefork pool worker）：注册 `celery.signals.worker_process_init` 信号，回调里再调 `reinit_file_logging(...)`。参数通过**环境变量**从父进程传（pool worker 由 Celery 内部 fork，闭包默认参数拿不到外层变量）：
  - `_WI1_LOG_QUEUE`、`_WI1_LOG_APP_NAME`、`_WI1_LOG_DIR`、`_WI1_LOG_MAX_BYTES`、`_WI1_LOG_BACKUP_COUNT`

> 这套机制在 `workers_common` 与聚合 broker 内部已完成，普通业务 Worker **无需自己处理**——用 `get_logger()` 打日志即可，确保 `configure_logging`/`reinit_file_logging` 调用链不被破坏。详见第 15 节。

### 14.8 新 Worker 接入聚合（完整清单）

让脚手架生成的新 worker 跑进 `make worker-in-one`，需手动几步：

1. **根 `pyproject.toml`**：`[tool.uv.workspace].members` 加 `workers/<worker>`，`[tool.uv.sources]` 加 `<worker> = { workspace = true }`。（脚手架 `generate-worker` 已自动做）
2. **`worker-in-one/pyproject.toml`** 的 `dependencies` 加 `"<worker>"`。
3. **`worker-in-one/src/worker_in_one/foundation/config.py`**：
   - `from <pkg>.foundation.config import Settings as <Pascal>Settings`
   - 加进 `Settings` 多继承基类列表
   - 写 `get_<worker>_settings()` 访问器（设 `MODEL="worker-in-one"`、`APP_NAME` 加后缀、`REDIS_PREFIX`，并把公共 `CELERY_*` 字段映射到 worker 专有前缀字段 `XXX_CELERY_*`）
4. **`worker-in-one/src/worker_in_one/workers.py`** 的 `workers_registry()` 加加载块：
   ```python
   from notify_worker.main import setup as notify_setup
   from notify_worker.handlers import register_all_handlers as notify_register
   worker_settings = _settings.get_notify_worker_settings()
   cleaner = await notify_setup(worker_settings, logger, shared_resources=shared_resources)
   cleaner_list.append(cleaner)
   specs.append(WorkerSpec(name="notify-worker", broker_type="celery",
                           register_handlers=notify_register, settings=worker_settings))
   ```
   非必需 worker 失败用 `logger.warning`，必需 worker 用 `raise RuntimeError`。
5. **若该 worker 有自定义队列**，在 `foundation/config.py` 的 `CELERY_QUEUE_CONCURRENCY` JSON 里加 `"{queue}": concurrency`。
6. **`deploy/Dockerfile.worker-in-one`**：加 `COPY workers/<worker> /workspace/workers/<worker>` 和 `RUN uv pip install --system -e ./workers/<worker> ...`。
7. **`deploy/scripts/migrate-worker.sh`**：若该 worker 有自己的执行元数据表（alembic），加 `run_migration "workers/<worker>" "<worker>"`。
8. `make worker-in-one` 启动验证，看日志 `Loaded worker: <worker>`。

### 14.9 配置与 env

`worker-in-one/foundation/config.py` 的 `Settings` 多继承 `WorkerInOneSettings`（= AppSettings+DatabaseSettings+RedisSettings+WorkersSettings）+ 各 worker 的 Settings。专有字段：

```python
APP_NAME = "worker-in-one"
MODEL = "worker-in-one"
WORKER_IN_ONE_SHARE_DB = True
WORKER_IN_ONE_SHARE_REDIS = True
CELERY_QUEUE_CONCURRENCY = '{"content_ops_worker.scene_task":2, ...}'   # 每队列并发 JSON
```

env 关键字段（`worker-in-one/env.example` / `deploy/config/worker-in-one.env.example`）：
- 共享开关：`WORKER_IN_ONE_SHARE_DB/REDIS=true`
- 每队列并发：`CELERY_QUEUE_CONCURRENCY={...}`
- OOM 守卫：`CELERY_WORKER_MAX_TASKS_PER_CHILD`、`CELERY_WORKER_MAX_MEMORY_PER_CHILD`、`CELERY_TASK_REJECT_ON_WORKER_LOST`
- broker：`CELERY_BROKER_URL`/`CELERY_BROKER_RESULT_BACKEND`（Redis db1/db2，与 all-in-one 一致）

---

## 15. 日志（重点：fork 后的日志修复）

日志是 Worker 最容易踩坑的地方，因为 Worker 有**两层 fork**（队列子进程 → Celery prefork pool worker）。共享库 `workers_common/logging.py` 已经处理好这个问题，但要理解原理，否则排错会无从下手。

### 15.1 日志库

`workers_common/logging.py`，structlog + JSON renderer（`ensure_ascii=False` 保留中文）。每个 processor 会注入 `request_id`、`operation`（每行必有）、`log_level`、时间戳。文件日志用 `RotatingFileHandler` + 后台线程 `QueueListener`：路径 `{log_dir}/{service_name}.log`，默认 100MB/100 备份。

`configure_logging(...)` 幂等，可多次调用。`reinit_file_logging()` 用于 fork 后重建 listener（见 15.3）。

### 15.2 问题：fork 不复制线程

> multiprocessing fork 只复制内存不复制线程：父进程的 QueueListener 线程在子进程内不存在，但 `_state.file_queue` 仍为非 None（内存复制），导致日志被投入队列却无人消费、永远不落盘。

两层 fork（队列子进程 → prefork pool worker）后 `QueueListener` 线程都没了，日志静默丢失——这是常见现象（某次"修复 worker 日志写入"提交正是解决它）。

### 15.3 修复方案

两处都调 `reinit_file_logging()` 重建 listener：

1. **队列子进程**（第一层 fork，`CeleryAggregateBroker._run_worker`）：调 `reinit_file_logging(service_name="{APP_NAME}-{queue}", ...)`。日志文件名变成 `{APP_NAME}-{queue}.log`（每队列一份）。
2. **prefork pool worker**（第二层 fork）：注册 Celery `worker_process_init` 信号，在 handler 里再调 `reinit_file_logging(...)`，参数从父进程通过环境变量传（形如 `_WI1_LOG_QUEUE`、`_WI1_LOG_APP_NAME`、`_WI1_LOG_DIR` 等）。

`reinit_file_logging()` 停掉旧 listener → 重置 `_state.file_queue`/`queue_listener` 为 None → 重建 `RotatingFileHandler` + `QueueListener`。优雅退出时调 `shutdown_file_logging()`。

> 这套机制在 `workers_common` 与聚合 broker 内部已完成，普通业务 Worker **无需自己处理 fork 日志**——只要用 `get_logger()` 打日志，并确保 `configure_logging` / `reinit_file_logging` 的调用链不被破坏即可。理解原理是为了在"日志莫名不落盘"时知道去哪查。

### 15.4 日志文件位置

- Worker-in-One 模式：`{LOG_DIR}/{APP_NAME}-{queue}.log`。Beat 与每队列各一份。
- Standalone 模式：`./logs/{APP_NAME}.log`。

### 15.5 日志使用约定

```python
from notify_worker.foundation.logging import get_logger
logger = get_logger(__name__)

logger.info("任务开始", operation="notify.send.start", task_id=tid)
logger.error("任务失败", operation="notify.send.fail", task_id=tid, error=str(e))
```

- **每条日志带 `operation=...`**（`<worker>.<resource>.<action>.<phase>`）。
- 上下文用结构化 kwarg，不要拼大段字符串。
- 敏感信息用 `workers_common` 提供的脱敏工具。

---

## 16. 容错与重试：分层故障模型

一个健壮的 Worker（尤其是长耗时、易失败的任务）应当有多层兜底。下面是一个推荐的分层模型，**轻量任务可只取 L2/L3，长任务建议全开**：

| 层 | 机制 | 作用 | 启用条件 |
|---|---|---|---|
| **L1** | Checkpoint | 每个阶段完成后存 checkpoint；崩溃重试从最近阶段恢复，不重头来 | 多阶段长任务 |
| **L2** | Celery retry | 任务异常自动重试（如 1min→5min→10min，max 3） | 所有任务 |
| **L3** | Worker 超时 | `CELERY_TASK_TIME_LIMIT` 硬超时，防止卡死 | 所有任务 |
| **L4** | Callback outbox | 终态结果先落盘 → 写 outbox → fire-and-forget HTTP 回调；回调失败留 outbox 待重试 | 需回调 Service 的任务 |
| **L5** | Beat outbox-scan | 定时扫描 outbox，重试未确认的回调 | 启用 L4 时配套 |

### 终态守卫（重要）

重试前先查 `<prefix>_task_execution`，若已是 `completed/failed/timeout`，**跳过任务体**，只重投 outbox——防止崩溃在回调阶段时把已完成的任务重跑一遍。

### 简单任务的取舍

不是每个 Worker 都需要五层。轻量任务可能只需 L2（Celery retry）+ L3（超时）。但**长耗时、多步骤、易崩溃的任务**（如跑几分钟到一小时的重活）必须上 checkpoint（L1）与 outbox（L4/L5）。下一节给出落地方案。

---

## 17. 进阶：长任务的可恢复执行（checkpoint + outbox）

> 模板默认不包含这套机制——它属于"长任务 Worker 按需自建"的进阶能力。如果你的任务几秒内能跑完且无需回调，跳过本节。如果你的任务多阶段、耗时长、需要崩溃恢复或回调 Service，照本节实现。

### 17.1 要解决的两个问题

1. **崩溃恢复**：长任务跑到 80% 时 worker 崩了，Celery 重试不该从 0 开始——需要 checkpoint 记录已完成的阶段，重试时跳过。
2. **可靠回调**：任务跑完要回调 Service，但 HTTP 可能失败——需要 outbox 先把终态落盘，再异步重试回调，保证"任务结果不丢"。

### 17.2 表结构（用 alembic 自建，表名带 `<prefix>_` 前缀）

- **`<prefix>_task_execution`**：`task_id` PK、`status`(pending/running/completed/failed/timeout)、`result`(落盘的终态结果)、`last_checkpoint`（最近完成阶段）、时间戳。**结果先写这张表**，保证终态可恢复。
- **`<prefix>_checkpoint`**：`task_id`、`stage`（阶段名）、`state`(JSON 阶段快照)、`stage_index`、`created_at`。唯一 `(task_id, stage)`，每个阶段一条最新快照。
- **`callback_outbox`**：`task_id`、`payload`(待回调内容)、`status`(pending/done)、`attempts`、`next_retry_at`、时间戳。
- **`dead_letter`**（可选）：重试耗尽的死信记录。

### 17.3 执行流程（在 application service 里编排）

```
1. handler 收到任务
   → 查 task_execution 终态守卫：已终态 → 跳过任务体，只重投 outbox
   → 通知 Service /started（running）

2. 恢复 or 新建
   → get_latest_checkpoint(task_id)
   → 有快照：从快照 rebuild 状态，跳过已完成的 stage
   → 无快照：新建状态，从第一个 stage 开始

3. 逐阶段执行（for stage in stages）
   → 若该 stage 已完成（来自恢复），continue
   → 执行 stage 业务
   → save_checkpoint(task_id, stage, state_snapshot)   # L1
   → （可选）notify Service 该 stage 进度

4. 终态
   → write task_execution(status=completed, result=...)  # 结果先落盘
   → enqueue callback_outbox(payload=终态)               # L4
   → fire-and-forget HTTP 回调 Service
   → 回调成功 → mark outbox done；失败 → 留 pending，等 Beat 重试 (L5)

5. Celery 重试耗尽
   → write dead_letter + 通知 Service failed
```

### 17.4 恢复的关键

- **checkpoint 写时机**：每个阶段**完成后**立即写（不是开始时），存该阶段的 state 快照（`state.model_dump(mode="json")`）。
- **恢复读时机**：任务启动时读最近一条 checkpoint，rebuild state，按 `stage_index` 跳过已完成的。
- **终态守卫**：恢复前先查 `task_execution`，已终态则**根本不进任务体**，直接重投 outbox。这条最容易被忘，但它防止"回调阶段崩溃 → 重试把整个任务重跑"。
- **清理**：完成后不立即删 checkpoint（便于排障与 outbox 重试窗口），靠定时 Beat（如每日凌晨）批量清理超过 TTL（如 90 天）的记录。

### 17.5 模型化阶段快照

阶段快照用一个 pydantic 模型表示任务的可恢复状态，每完成一个 stage 更新它并 `model_dump(mode="json")` 存库；恢复时 `YourStateModel.model_validate(checkpoint["state"])` 重建。这比把一堆零散字段塞进 dict 更安全、可演进。

---

## 18. Beat 定时任务

Celery Beat 做周期任务（替代 cron）。配置在 Worker 的 `Settings`：

```python
CELERY_BEAT_ENABLE: bool = True
CELERY_BEAT_SCHEDULE: dict = {
    "outbox-scan": {
        "task": "notify_worker.outbox_scan",      # topic（也是 handler）
        "schedule": {"timedelta": {"minutes": 5}},     # 或 {"crontab": {...}} 或 int 秒
    },
    "daily-cleanup": {
        "task": "notify_worker.daily_cleanup",
        "schedule": {"crontab": {"minute": 0, "hour": 4}},
    },
}
```

`resolve_schedule`（聚合器内部）会把 dict 形式转成 Celery 的 `timedelta`/`crontab` 对象。

要点：
- standalone 模式下 Beat 与 worker 在同一进程（`--beat`）；聚合模式下**只有第一个队列子进程**带 Beat，避免重复触发。
- Beat 任务也是普通 handler，topic 注册进 `registry.py`、路由进 `CELERY_TASK_ROUTES`。
- 典型 Beat 用途：outbox 重试扫描（每 5min）、卡住任务扫描、执行元数据清理（每日）。

---

## 19. Producer 端：Service 如何投递任务

Worker 是 consumer，producer 在 Service 侧。投递用 `services_common.task_publisher`（封装 `celery.send_task`）。理解这一节能帮你把 Service 和 Worker 的协议对齐。

### 19.1 Service 端典型代码

```python
# 某个 Service 里，dispatch 一个任务到 Worker
class MyDispatcher:
    @inject
    def __init__(self, manager: TaskPublisherManager):
        self._manager = manager

    def dispatch_some_task(self, payload: dict):
        self._manager.send(
            broker_name="celery",
            topic="notify_worker.send_email",   # Worker 的 topic（两端一致）
            payload=payload,
            queue="notify_worker.email.send",                            # 路由到的队列
        )
```

`TaskPublisherManager.send` 内部 `celery.send_task(topic, kwargs=payload, queue=...)`。

### 19.2 协议对齐（三处必须两端一致）

- **topic 字符串**：Service 写 `send_task("notify_worker.send_email")`，Worker 在 `register_handler("notify_worker.send_email", handler)` 注册。
- **payload 用 kwargs 风格**（`send_task(..., kwargs={...})`），Worker handler 用 `**kwargs` 收（推荐）。
- **队列名**：Service 指定 `queue="notify_worker.email.send"`，Worker 的 `CELERY_TASK_ROUTES` 把该 topic 路由到同名队列。

### 19.3 Worker 作为 producer（子任务自分发）

Worker 内部也可投递子任务给**自己**消费（fan-out）。在 Worker 的 `infrastructure/` 里写一个轻量 dispatcher，用 Celery `current_app.send_task(...)` 把子任务投到某个队列，同一 Worker 消费。这是"producer = consumer"的自分发模式，适合把一个大任务拆成多个独立子任务并行处理。

---

## 20. 端到端任务流（通用示例）

把前面串起来，追一个通用任务（Worker `notify-worker` 的 `send_email` 任务）的完整生命周期：

```
1. Service 投递
   某个 Service 收到业务请求
     → 组装 payload: { task_id, to, subject, body, ... }
     → dispatcher.dispatch_some_task(payload)
     → celery.send_task("notify_worker.send_email",
                         kwargs=payload, queue="notify_worker.email.send")

2. 路由
   Worker 的 NTF_CELERY_TASK_ROUTES:
     "notify_worker.send_email" → queue "notify_worker.email.send"

3. 消费
   Worker-in-One: 队列 "notify_worker.email.send" 的 fork 子进程 (按 CELERY_QUEUE_CONCURRENCY 配并发)
     → 注册的 task handle_send_email 触发
     → raw = dict(payload) / dict(kwargs)
     → asyncio.run(_async_send(req)) 或常驻 loop 桥接
     → 取 injector → 调 NotifyService.send_email(req)
     → 内部: 写 ntf_task_execution(running) → 调 email client → 更新终态

4. 结果回传（若需回调 Service）
   简单任务: 直接返回 result（Celery result backend 可查）
   需回调任务: 终态先落 task_execution → 入 callback_outbox → fire-and-forget HTTP 回调
              回调失败 → outbox_scan Beat (每5min) 重试 (L5)
              Celery 重试耗尽 → 写 dead_letter, 通知 Service failed

5. Service 处理回调
   Service 收回调, 更新业务表终态, 落业务数据
```

这就是一个 Worker 任务从被投递到回传结果的全链路。轻量任务走"直接返回"即可，长任务才需要 outbox/checkpoint 兜底（见第 16–17 节）。

---

## 21. 新增一个任务（实战 walk-through）

假设在 `notify-worker`（前缀 `ntf`）加一个"发邮件"任务。

### 步骤 1：domain

```python
# app/domain/entities/notification.py
class Notification(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    notification_id: str
    to: EmailAddress            # VO
    subject: str
    body: str
    status: str = "pending"
    sent_at: datetime | None = None

# app/domain/repositories/notification_repository.py
class NotificationRepository(ABC):
    @abstractmethod
    async def create(self, n: Notification) -> Notification: ...
    @abstractmethod
    async def update_status(self, notification_id: str, status: str) -> None: ...
```

### 步骤 2：infrastructure

```python
# app/infrastructure/persistence/models/notification_model.py
class NTFNotificationModel(BaseModel):
    __tablename__ = "ntf_notification"   # ⚠️ 前缀（全小写表名）；类名用全大写前缀 {PREFIX_UPPER}
    notification_id = Column(String, primary_key=True)
    to = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="pending")
    sent_at = Column(DateTime, nullable=True)

# app/infrastructure/persistence/repositories/sql_notification_repository.py
class SQLNotificationRepository(NotificationRepository):
    @inject
    def __init__(self, dm: DatabaseManager, log_manager: LogManager): ...
    async def create(self, n): ...   # _to_model / _to_entity
    async def update_status(self, nid, status): ...

# app/infrastructure/modules.py 加绑定
binder.bind(NotificationRepository, to=SQLNotificationRepository, scope=None)
```

加迁移：`make migration-create-worker WORKER=notify-worker NAME=create_notification` → 检查 → `make migrate-worker WORKER=notify-worker`。

### 步骤 3：clients（发邮件的外部服务）

```
clients/email_service/
├── interface.py      # EmailClient(ABC): async send(...) -> SendResult
├── schemas.py        # SendResult
├── remote_api.py     # RemoteEmailClient (httpx)
├── local_api.py      # LocalEmailClient (worker-in-one 模式, 若有本地实现)
└── api_proxy.py      # EmailServiceAPIProxy (按 MODEL 切)
# clients/modules.py 加绑定
```

### 步骤 4：application

```python
# app/application/services/notify_service.py
@inject
class NotifyService:
    def __init__(self, repo: NotificationRepository, email: EmailServiceAPIProxy, dm: DatabaseManager):
        self.repo = repo; self.email = email; self.dm = dm

    async def send_email(self, req: SendEmailRequest) -> SendEmailResult:
        n = Notification(notification_id=generate_id(), to=EmailAddress(req.to),
                         subject=req.subject, body=req.body)
        saved = await self.repo.create(n)
        try:
            result = await self.email.send(to=str(saved.to), subject=saved.subject, body=saved.body)
            await self.repo.update_status(saved.notification_id, "sent")
            return SendEmailResult(notification_id=saved.notification_id, status="sent")
        except Exception:
            await self.repo.update_status(saved.notification_id, "failed")
            raise    # 触发 Celery 重试 (L2)

# app/application/modules.py 加绑定
binder.bind(NotifyService, to=NotifyService, scope=None)
```

### 步骤 5：handler + registry

```python
# handlers/send_email.py
def handle_send_email(self, payload=None, **kwargs):
    raw = dict(payload) if payload else dict(kwargs)
    logger.info("Received send_email task", payload=raw)
    try:
        req = SendEmailRequest(**raw)      # 转模型，校验
        result = asyncio.run(_async_send(req))
        return result.model_dump()
    except Exception as e:
        logger.error("send_email task failed", error=str(e), payload=raw)
        raise

async def _async_send(req: SendEmailRequest) -> SendEmailResult:
    injector = get_injector()
    service = injector.get(NotifyService)
    return await service.send_email(req)
```

```python
# handlers/registry.py
def register_all_handlers(broker):
    from notify_worker.handlers.send_email import handle_send_email
    broker.register_handler("notify_worker.send_email", handle_send_email)
```

### 步骤 6：配置路由 + 超时

```python
# foundation/config.py
NTF_CELERY_TASK_DEFAULT_QUEUE: str = "notify_worker.email.send"
NTF_CELERY_TASK_ROUTES: dict = {
    "notify_worker.send_email": {"queue": "notify_worker.email.send"},
}
NTF_CELERY_TASK_QUEUES: str = "notify_worker.email.send"
CELERY_TASK_TIME_LIMIT: int = 120
CELERY_TASK_SOFT_TIME_LIMIT: int = 100
```

env.example 加：
```
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_BROKER_RESULT_BACKEND=redis://localhost:6379/2
OTHER_SERVICE_URL=...   # 若调 Service
EMAIL_SERVICE_URL=http://localhost:8030
```

### 步骤 7：验证

```bash
make dev-worker WORKER=notify-worker
# 另起终端投递（用 Celery 或 Service 端 send_task）：
# topic="notify_worker.send_email", queue="notify_worker.email.send"
```

### 步骤 8：lint/test

```bash
make lint-worker WORKER=notify-worker
make test-worker WORKER=notify-worker
```

---

## 22. 测试与 Lint

```bash
make lint-worker WORKER=xxx     # ruff + mypy
make test-worker WORKER=xxx     # pytest
make migrate-worker WORKER=xxx
make migration-create-worker WORKER=xxx NAME=add_xxx
make docker-build-worker WORKER=xxx
```

### 测试要点

- handler 是同步函数包裹 async，可单独测：构造 `raw` dict，mock `get_injector().get(NotifyService)` 返回一个 mock service，调 `handle_send_email(None, **raw)` 断言返回。
- application/domain 层测试：自建局部 `Injector`，mock `DatabaseManager`/`RedisManager`/clients，断言业务逻辑。
- 集成测试：`make compose-up` 起真实 Redis + PG，投真实任务验证端到端。
- checkpoint 恢复测试（若实现了）：模拟中途抛异常 → 重投 → 断言从最近阶段续跑（而非重头）。

ruff/mypy 配置同 Service（`line-length=100`、`py312`、`strict=true`）。

---

## 23. 编码规范与提交前检查清单

### 规范要点（承接 Service 规范 + Worker 特有）

- **`workers/` 不得 import `services_common`**。用 `workers_common`。
- **handler 同步签名** `def handler(self, payload=None, **kwargs)`，桥接 async，业务逻辑在 application 层。
- **队列边界才允许裸 dict**；进 application 前转 pydantic。
- **一个任务一个 handler 文件**；topic 命名 `{pkg}.{task}`（两段点分 snake）。
- **队列路由用前缀字段**（`<PREFIX>_CELERY_*`），启动覆盖到 `CELERY_*`。
- **ORM 表名带前缀**（`<prefix>_<表>`，全小写）；**ORM 类名带全大写前缀** `<PREFIX_UPPER><表>Model`（如 worker_prefix=`ntf` → `NTFNotificationModel`，表名 `ntf_notification`）；DB 操作必 async。详见 `ai-coding-worker-app.md` §8（worker-in-one 多服务共用同一 `DeclarativeBase`，类名不带前缀会冲突）。
- **clients 五件套**；`app/`/`handlers/` 不直接 import httpx。
- **新增依赖登记**对应 `modules.py`。
- **日志每条带 `operation=`**；fork 场景注意 `reinit_file_logging` 调用链不被破坏。

### 提交前清单

- [ ] 未 import `services_common`（用 `workers_common`）
- [ ] 目录结构合规（`handlers/` + `app/{application,domain,infrastructure}` + `foundation` + `clients` + `pkg`）
- [ ] handler 同步签名 + 桥接 async；业务逻辑在 application 层
- [ ] 队列边界外无裸 dict；payload 进 application 前转模型
- [ ] ORM 表名带前缀（全小写）；ORM 类名带全大写前缀 `<PREFIX_UPPER><表>Model`；Repository 返回 Entity，有 `_to_entity`/`_to_model`
- [ ] clients 五件套；`app/`/`handlers/` 无 httpx
- [ ] 新依赖在 `modules.py` 注册；topic 在 `registry.py` 注册
- [ ] `CELERY_TASK_ROUTES` 配了 topic→queue；超时配置合理
- [ ] 长任务有 checkpoint + outbox 兜底；终态守卫到位
- [ ] 日志带 `operation=`；fork 场景日志能落盘
- [ ] `make lint-worker` 过；`make test-worker` 过
- [ ] 接入 Worker-in-One 时已在 `worker-in-one/.../workers.py` 注册

> 等价于 `develop/ai-coding-worker-app.md` 的 checklist，提交前对照。

---

## 24. 从开发到部署

> ⚠️ 同 Service 指南：README 提到 `infrastructure/`、`make deploy`、k8s 等存在文档漂移，实际部署资产在 `deploy/`。

### 24.1 本地依赖

```bash
make compose-up      # PostgreSQL + Redis（Redis 是 Celery broker，必需）
```

### 24.2 单 Worker 镜像

某些 Worker 有独立 Dockerfile（自包含构建）。多数 Worker 走聚合镜像（下一节）。

### 24.3 Worker-in-One 生产部署（主流）

生产用 `make worker-in-one` 或直接 `python -m worker_in_one.main`。部署资产：

- `deploy/Dockerfile.worker-in-one`：聚合镜像
  - base `python:3.12-slim`，装系统依赖、uv
  - `COPY` `workers/common`、各 worker、`worker-in-one` 进 `/workspace`
  - 按依赖顺序 `uv pip install --system -e`（common → 各 worker → worker-in-one）
  - 创建非 root 用户
  - Healthcheck：`pgrep -f "worker_in_one"`（**无 HTTP 端口**，靠进程探测）
  - `CMD ["python", "-m", "worker_in_one.main"]`
- `deploy/scripts/deploy-worker-in-one.sh`：薄封装，`SERVICES="worker-in-one" exec deploy.sh "$@"`
- `deploy/scripts/migrate-worker.sh`：迁移
- `deploy/config/worker-in-one.env(.example)`：生产环境变量（共享 DB/Redis、`WORKER_IN_ONE_SHARE_DB/REDIS=true`、`CELERY_QUEUE_CONCURRENCY` JSON、OOM 守卫等）

### 24.4 典型上线流程

```bash
# 1. 构建聚合镜像（仓库根）
# 2. 配 deploy/config/worker-in-one.env
#    - CELERY_BROKER_URL / RESULT_BACKEND 指向生产 Redis
#    - DATABASE_URL / REDIS_URL 指向生产
#    - CELERY_QUEUE_CONCURRENCY 按队列配并发
#    - WORKER_IN_ONE_SHARE_DB/REDIS=true
# 3. 部署（脚本内部：拉镜像 → migrate-worker.sh → 启动 → 进程健康检查）
deploy/scripts/deploy-worker-in-one.sh
```

### 24.5 不要忘了

- 启动前**跑迁移**（`migrate-worker.sh`，建 `<prefix>_task_execution`/checkpoint/outbox 等表）。
- 健康检查靠 `pgrep`（进程级），无 `/health` 端口。
- 生产日志 `LOG_FILE=true`、`LOG_DIR` 指向持久卷（fork 后 `reinit_file_logging` 会按 `{APP_NAME}-{queue}.log` 落盘）。
- OOM 守卫：`worker_max_tasks_per_child=50`、`worker_max_memory_per_child=2_000_000` KB。
- Redis broker 与 result backend 用不同 DB 号（如 `/1` 与 `/2`），避免和业务 Redis 缓存（`/0`）冲突。
- 回滚见 `deploy/README.md`。

---

## 25. 常见坑与排错

| 现象 | 原因 / 解决 |
|---|---|
| `ModuleNotFoundError: services_common` | Worker 误 import 了 `services_common`。改用 `workers_common`。Worker 边界红线。 |
| 任务投了没消费 | topic 两端不一致；或 queue 路由没配；或 Worker 没起该队列的消费者。查 `CELERY_TASK_ROUTES` 与 `register_handler` 的 topic 字符串。 |
| handler 报 `Injector not initialized` | `setup()` 没跑或失败。standalone 模式确认 `run_worker()` 里 `asyncio.run(setup(...))` 在 `start_all()` 前。 |
| 日志不落盘（worker-in-one） | fork 后 QueueListener 丢失。确认 `reinit_file_logging` 在两层 fork 都被调；查 env 变量是否传到子进程。 |
| 长任务崩溃后重试从头来 | 没用 checkpoint，或 checkpoint 写时机不对（应在每阶段**完成后**写）。见第 17 节。 |
| 重试把已完成任务又跑一遍 | 缺终态守卫。重试前查 `task_execution`，终态则跳过任务体只重投 outbox。 |
| 回调 Service 一直失败 | outbox 没生效或 Beat 没起。确认 `callback_outbox` 写入 + `outbox_scan` Beat 在跑。 |
| `asyncpg` 报连接已关闭 | 用 `asyncio.run()` 跑长任务导致 loop 关闭后连接池失效。改用常驻 event loop。 |
| Beat 任务重复触发 | 聚合模式下多个队列子进程都带了 `--beat`。确认只有第一个队列子进程带 `--beat`。 |
| 慢队列拖死快队列 | 没按队列 fork 隔离，或并发配置不当。确认 `CELERY_QUEUE_CONCURRENCY` 每队列独立配。 |
| Worker 自分发子任务不消费 | 子任务 topic 没在 `registry.py` 注册，或路由到不存在的队列。 |
| mypy strict 报错 | 补类型注解；handler 返回类型、Repository 都要标。 |

---

## 26. 附录：命令速查表

```bash
# ── 创建 Worker ──
make generate-worker WORKER=xxx SHORT_PREFIX=yy
make install-worker WORKER=xxx-worker

# ── 单 Worker 开发 ──
make dev-worker WORKER=xxx-worker         # python -m <pkg>.main
make dev-watch-worker WORKER=xxx-worker   # watchfiles 自动重启
make lint-worker WORKER=xxx-worker        # ruff + mypy
make test-worker WORKER=xxx-worker
make migrate-worker WORKER=xxx-worker
make migration-create-worker WORKER=xxx-worker NAME=add_xxx
make docker-build-worker WORKER=xxx-worker

# ── 聚合 ──
make worker-in-one                        # 所有 Worker 一个进程
make worker-in-one-watch
make worker-in-one-install

# ── 本地依赖 ──
make compose-up                           # PostgreSQL + Redis
make compose-down

# ── 部署（deploy/ 下）──
# deploy/scripts/deploy-worker-in-one.sh
# deploy/scripts/migrate-worker.sh
# deploy/Dockerfile.worker-in-one
```

---

> 下一步阅读：
> - `develop/service-development-guide.md` — Service 开发指南（姊妹篇，DDD 基础在此）
> - `develop/ai-coding-worker-app.md` — Worker 完整约束规范（红线全集）
> - `workers/pingpong-worker/` — Worker 参考模板，对照本文读源码
> - `workers/common/` — 共享库 `workers_common`（broker 抽象、DB/Redis、日志、配置）

# AI 编程约束范式 - Worker（workers/）开发规范

> **重要提醒**：在开发 `workers/` 下的任何 worker 时，你必须严格逐条遵循本规范。本规范的目标与 service 规范一致——**消除每次开发的差异性**。
>
> **Worker 与 Service 同源**：worker 复用 service 的全部分层架构（domain / application / infrastructure / clients / foundation）。**这些层的约束与 `develop/ai-coding-service-app.md` 完全一致**，本规范不再重复，只描述 **worker 的差异部分**：入口层（`handlers/`）、无 HTTP、broker 抽象（共享于 `workers_common.broker`）、运行模型。
>
> 凡涉及 domain/application/infrastructure/clients 的写法（分层依赖矩阵、四类数据载体、禁止裸 dict、SOLID 文件拆分、DI 注册、命名），**一律以 service 规范为准**。

---

## 0. Worker 与 Service 的本质差异

| 维度 | Service | Worker |
|---|---|---|
| 触发方式 | HTTP 请求（FastAPI） | 消息队列任务（Celery 等 broker） |
| 入口层 | `app/api/v1/`（endpoints/schemas/router） | `handlers/`（任务处理器）；broker 抽象在 `workers_common.broker`（worker 本地**无** `broker/` 目录） |
| 对外契约 | HTTP DTO + `DataResponse` | 任务 payload（dict in）→ 结果 dict out |
| 端口 | 有 `PORT` | **无端口**，由 broker 拉取任务驱动 |
| 启动入口 | uvicorn / FastAPI app | `run_worker()` → `BrokerManager.start_all()` |
| 配置基类 | `services_common.config`（含 HOST/PORT/CORS） | `workers_common`（`WorkersSettings`，无 Web 字段） |
| 运行并发 | ASGI 协程 | Celery `--pool=threads`（或 prefork），handler 同步入口内用 `workers_common.async_bridge.run_async()`（工作线程 thread-local 持久 loop，见 §4.1） |

> **核心心智模型**：把 worker 的 `handlers/` 当作 service 的 `api/endpoints/` 的等价物——它是入口适配层，只做"解析 payload → 调用 application → 返回结果"，**不写业务逻辑**。

## 0.1 占位符与命名推导（与 service 规范 §0.1 同源）

worker 的占位符推导来源：`worker_name` 与 `worker_prefix`（无 `service_code`/`port`）。

> ⚠️ **关于 `worker.metadata`**：`generate-worker` 脚本会写一个 `worker.metadata` 文件（含 `worker_name`/`worker_prefix`），但它是给工具/查重读的，**运行时不读**。前缀在运行时来自 `foundation/config.py` 的 `REDIS_PREFIX` 与 `PIPO_CELERY_*` 字段（脚手架替换）。`pingpong-worker` 作为模板本身不带 `worker.metadata`（模板占位），生成新 worker 时脚本会写。AI 改写时以前缀（如 `ntf`）为基准即可，无需依赖 `worker.metadata` 存在。

设新 worker `notify`，`worker_prefix = "ntf"`：

| 占位符 | 推导规则 | 本例取值 | 用在哪里 |
|---|---|---|---|
| `{kebab}` | `worker_name` 的 `_` → `-` | `notify` | worker 目录 `{kebab}-worker` |
| `{snake}` | `worker_name`（snake） | `notify` | 包目录 `{snake}_worker` |
| `{pkg}` | = `{snake}_worker` | `notify_worker` | **所有 import 根** |
| `{pascal}` | `worker_name` 各段首字母大写 | `Notify` | 服务级类名 `class {Pascal}Service` |
| `{prefix}` | `worker_prefix`（全小写） | `ntf` | **表名前缀** `ntf_xxx`、Redis 前缀、队列名前缀、`{PREFIX}_CELERY_*` 配置前缀 |
| `{PREFIX_UPPER}` | `{prefix}` 全大写 | `NTF` | **ORM 类名前缀** `class {PREFIX_UPPER}{表}Model` → `NTFNotificationModel`；Celery 配置前缀 `NTF_CELERY_TASK_ROUTES` 等 |
| `{domain}` | 任务的业务域 | `notify` | handler 文件 `{域}_handler.py`、队列第 2 段 `{domain}` |

**硬约束**（与 service §0.1 一致）：
- ORM 类名前缀一律用 `{PREFIX_UPPER}` —— **`worker_prefix` 整体转全大写**（不是首字母大写）。`ntf`→`NTF`、`pipo`→`PIPO`。
- 表名前缀用 `{prefix}`（全小写）。类名前缀（全大写）与表名前缀（全小写）来自同一个 `worker_prefix`，仅大小写不同：表 `ntf_notification` ↔ 类 `NTFNotificationModel`、表 `pipo_ping` ↔ 类 `PIPOPingModel`。
- ❌ **不要**把 ORM 类名前缀写成首字母大写（`NtfNotificationModel`）或无前缀（`NotificationModel`）。目的见 §8：all-in-one / worker-in-one 合并运行时多个服务共享同一 SQLAlchemy `DeclarativeBase`，类名不带前缀或前缀风格不统一都会冲突。
- import 根一律 `{pkg}`（如 `from notify_worker.app.domain...`）。
- `generate-worker` 后包名/前缀/import 根已正确，**AI 不得重命名目录或顶层包**。

## 0.2 脚手架后的改写流程（收到新 worker 需求时的操作序列）

`generate-worker` 后的 worker 继承了 pingpong 的 demo：`handlers/pp_demo.py`（重命名为 `{域}_demo.py`）、`run_worker()` 里 `PIPO_CELERY_*` 字段、`app/application/services/pp_service.py` 等。按下列流程改写：

**第一步：确定任务与用例**（先区分两类入口）
1. 列出本 worker 的任务：**消费型任务**（队列消息触发，签名 `handle_xxx(self, payload, **kwargs)`）有哪些？**Beat 定时任务**（见 §4.5，签名 `handle_xxx(self, **kwargs)` 无 payload）有哪些？每类一个 handler + 一个 topic。
2. 每个任务的用例归类按 service §5.2 决策树（单聚合写→command；跨聚合→service；只读→query）。
3. 区分外部依赖：本 worker 自己的执行元数据库（→infrastructure），调别的 service/第三方（→clients，**不得进 infrastructure**）。

**第二步：清理 demo 代码**（逐文件确认，注意"保留 vs 删除"）

删除/清空的 demo（无对应业务时）：
- `handlers/pp_demo.py` + `registry.py` 里 `pingpong_worker.pingpong` 注册行
- `handlers/beat_demo_handler.py` + `registry.py` 里 `BEAT_DEMO_TOPIC` 注册与常量（若本 worker 无 Beat 任务）
- `app/application/services/pp_service.py`、`commands/`、`queries/` 的 demo，`app/application/modules.py` 同步移除对应 `binder.bind`
- `app/domain/` 的 `entities/ping.py`、`repositories/{ping,pong}_repository.py`、`value_objects/{ping_message,pong_data}.py`、`caches/pp_cache.py`
- `app/infrastructure/` 的 `persistence/models/{ping,pong}_model.py`、`persistence/repositories/sql_{ping,pong}_repository.py`、`caches/pp_redis_cache.py`、`security/password.py`，`infrastructure/modules.py` 同步移除对应 `binder.bind`

**必须保留**（worker 基础设施，勿删）：
- `handlers/schemas.py`（若无则按 §4.2 新建）
- `foundation/{config,container,logging}.py`（改值不删文件）
- async 调度无需本地文件：`run_async` 来自 `workers_common.async_bridge`（§4.1），worker 本地**不应有** `_loop.py`

改前缀（`pipo`/`PIPO` → 本 worker 前缀）：
- `foundation/config.py`：`REDIS_PREFIX`、`PIPO_CELERY_*` 字段名与值、`PIPO_CELERY_BEAT_SCHEDULE`（若有）
- `main.py` 的 `run_worker()`：前缀覆盖语句 `PIPO_CELERY_*` → `{PREFIX}_CELERY_*`
- `clients/other_service/api_proxy.py`：`setting.MODEL == "all-in-one"` → `== "worker-in-one"`（§6 模板偏差）

**第三步：按附录 A 结构新建业务文件**，每新增可注入类立即在对应 `modules.py` 注册（§6.1.1 约定同样适用）。
**第四步：alembic 迁移**（若新增执行元数据表）。
**第五步：对照 §10 清单核对。**

> 判据：交付后 grep 不到 `pingpong`/`pp_demo`/`PIPO`（前缀占位）残留 = 改写干净。

---

## 1. 项目结构规范

```
{worker名}-worker/
├── src/
│   └── {worker名_underscore}_worker/
│       ├── app/                            # 与 service 完全一致的分层
│       │   ├── application/                # 应用层 (CQRS)
│       │   │   ├── commands/               # 写用例（单聚合写，逻辑写这里）
│       │   │   ├── queries/                # 读用例（只读，可投影读模型）
│       │   │   ├── services/               # 应用服务（跨聚合/多步流程/可复用编排）
│       │   │   ├── common/
│       │   │   └── modules.py
│       │   ├── domain/
│       │   │   ├── entities/
│       │   │   ├── value_objects/
│       │   │   ├── repositories/
│       │   │   ├── caches/
│       │   │   ├── common/
│       │   │   └── modules.py
│       │   └── infrastructure/
│       │       ├── persistence/
│       │       │   ├── models/
│       │       │   └── repositories/
│       │       ├── caches/
│       │       ├── security/
│       │       └── modules.py
│       ├── handlers/                       # 【Worker 特有】任务处理器（入口层）
│       │   ├── __init__.py                 # 导出 register_all_handlers
│       │   ├── registry.py                 # 集中注册 topic → handler
│       │   ├── schemas.py                  # handler 专用 payload/result 模型（必备，见 §4.2）
│       │   # 注：async 调度统一用 workers_common.async_bridge.run_async（见 §4.1），
│       │   # worker 本地不再有 _loop.py —— 持久 loop 实现收敛在通用层
│       │   ├── {域}_handler.py             # 消费型任务处理器（一类任务一文件）
│       │   └── {域}_beat_handler.py        # Beat 定时任务处理器（按需，见 §4.5）
│       ├── clients/                        # 与 service 一致
│       │   └── modules.py
│       ├── foundation/                     # 基础组件
│       │   ├── config.py                   # 含 WorkersSettings
│       │   ├── container.py
│       │   └── logging.py
│       └── pkg/                            # 纯工具
├── alembic/
├── tests/
├── pyproject.toml
├── Dockerfile
└── Makefile
```

> ⚠️ **Worker 没有 `app/api/` 目录，也没有本地 `broker/` 目录**。入口层是与 `app/` 平级的 `handlers/`（在包根下，不在 `app/` 内）。broker 抽象统一在 `workers_common.broker`，worker 直接 `from workers_common.broker import BrokerManager`，**不建本地 `broker/` 转发层**。

---

## 2. 入口层数据流（核心）

```
消息队列 → broker(消费 topic) → handler(同步入口, run_async) → _async_xxx → application(command/query/service) → domain ← infrastructure
                                                                          ↓
                                                                      clients
```

- broker 负责**协议适配**（连接队列、序列化、注册 topic、拉取消费）。
- handler 负责**入口适配**（解析 payload、调度异步、组装结果），等价于 service 的 endpoint。
- 业务逻辑全部下沉到 `application` 及以下，与 service 规范完全一致。

---

## 3. Broker 层规范（`broker/`）

## 3. Broker 层规范（共享于 `workers_common/broker/`）

### 3.1 架构：统一收敛在通用层，worker 本地无 broker 目录

Broker 的抽象基类、工厂、注册表和实现**统一收敛在 `workers_common/broker/`**，不在各 worker 内重复存放，**各 worker 本地不建 `broker/` 目录**：

```
workers/common/src/workers_common/broker/     # 通用层（唯一实现所在地）
├── __init__.py          # 导出 BaseBroker / BrokerManager 等
├── base.py              # BaseBroker (ABC)
├── factory.py           # 工厂 + BROKER_REGISTRY 注册表
├── manager.py           # BrokerManager（多 broker 统一管理）
└── implementations/     # 具体实现（一中间件一文件）
    └── celery_broker.py
```

worker 直接 `from workers_common.broker import BrokerManager`（见 §5 `run_worker()`），**不建本地 `broker/` 转发层**。

所有中间件实现统一接口，禁止 handler / application 直接依赖具体中间件 SDK。

### 3.2 抽象基类（`workers_common/broker/base.py`）

```python
from abc import ABC, abstractmethod
from typing import Any, Callable


class BaseBroker(ABC):
    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def register_handler(self, topic: str, handler: Callable) -> None: ...

    @abstractmethod
    def send_task(self, topic: str, payload: dict[str, Any], **kwargs) -> Any: ...
```

### 3.3 工厂 + 注册表（`workers_common/broker/factory.py`）

- 用 `BROKER_REGISTRY: dict[str, str]`（type → 类路径）实现"开闭原则"：**新增中间件只加注册表条目 + 新增实现文件，不改已有代码**。
- `create_broker(broker_type="celery", settings=...)` 显式指定类型创建实例。
- `CeleryBroker` 通过 `getattr(settings, key, default)` 动态读取配置，各 worker 继承 `workers_common.WorkersSettings` 并覆盖专属字段，无需改动通用层。

```python
BROKER_REGISTRY: dict[str, str] = {
    "celery": "workers_common.broker.implementations.celery_broker.CeleryBroker",
    # "rabbitmq": "workers_common.broker.implementations.rabbitmq_broker.RabbitMQBroker",
}


def create_broker(settings=None, *, broker_type="celery", config=None) -> "BaseBroker":
    ...
    return broker_cls(config or settings)
```

### 3.5 Broker 禁止事项

- ❌ handler / application / domain / infrastructure 直接 import `celery` 等中间件 SDK。
- ❌ 在 broker 实现里写业务逻辑（broker 只做协议适配与生命周期）。
- ❌ 新增中间件时修改 `BaseBroker` 或既有实现类的内部分支（应新增文件 + 注册表条目）。
- ❌ **在 worker 本地建 `broker/` 目录重复存放 BaseBroker / 工厂 / 实现**（统一在 `workers_common.broker`，worker 直接 import 即可）。

---

## 4. Handlers 层规范（`handlers/`，等价于 service 的 endpoints）

### 4.1 职责与异步调度（统一 `run_async`，禁止 `asyncio.run`）

解析 payload → 调度异步 → 调用 application → 组装返回结果。**严禁写业务逻辑**。

- 一类任务一个文件：`handlers/{域}_handler.py`（消费型）或 `{域}_beat_handler.py`（Beat 定时，见 §4.5）。
- Celery handler 是**同步函数**（`def handle_xxx(self, ...)`，`bind=True` 故首参为 `self`）。
- **统一用 `workers_common.async_bridge.run_async()` 调度异步**，**禁止** `asyncio.run()`。

⚠️ **为什么禁止 `asyncio.run`（关键运行时陷阱）**：Celery 在同步 prefork 进程执行 handler；`asyncio.run()` 每次创建并关闭一个新 event loop，而 `DatabaseManager` 的 `asyncpg` 连接池**会绑定到创建它的 loop**。loop 关闭后连接池失效，下一个任务再 `asyncio.run` 会触发"连接池绑定到已关闭 loop"的运行时崩溃。`async_bridge` 用**当前工作线程的 thread-local 持久 loop**：`run_async` 直接在工作线程上 `loop.run_until_complete(coro)`，loop 创建一次、**跨任务复用、不关闭**，asyncpg/redis.asyncio 连接池绑一次即持续有效。

`run_async` 的实现收敛在通用层 `workers_common.async_bridge`（**不是 worker 本地文件**），`from workers_common.async_bridge import run_async` 即可。**不要自实现 `run_async`、不要在 worker 本地建 `_loop.py`**。该模块的实现要点（无需仿写，理解即可）：
- **thread-local 持久 loop**：每个工作线程惰性建一个 `asyncio` loop 并复用；Celery threads pool「一个工作线程同时只跑一个任务」，故同一 loop 不会并发 `run_until_complete`，历史上「module-global loop 多线程共享 → This event loop is already running」的崩溃不再发生。
- **直接驱动，无后台线程**：在拥有该 loop 的工作线程上 `run_until_complete`，而非后台 `run_forever` + `run_coroutine_threadsafe`（后者若无 driver 线程会永久挂死）。`contextvars.copy_context()` 给每个任务上下文隔离，in-task 写不会泄漏给同线程下一个任务。
- **禁重入**：`run_async` 只能在同步入口（handler 顶层）调用；在 coroutine 内再调 `run_async` 会抛 `RuntimeError`（重入会死锁）。
- **双模兼容**：同一 `run_async` 在 `--pool=threads`（thread-local loop）和 prefork（单线程驱动、退化为「每进程一个 loop」）下都正确，无回归。
- **禁止跨调用泄漏后台任务**：任何 `asyncio.create_task` 必须在顶层 coroutine 返回前 await 或 cancel——worker 代码满足此约束（`RedisWorkerLock` 的 backgrouund renew 只在 FastAPI 服务的 uvicorn loop 上用，不进 worker）。

> 生命周期钩子（`install_shutdown_hook` / `dispose_thread_loop`）在 worker `setup()` 里由通用层注册，handler 层无需关心，见 §5。

```python
# handlers/{域}_handler.py  —— 消费型 handler 标准形态
from typing import Any

from {pkg}.foundation.container import get_injector
from {pkg}.foundation.logging import get_logger
from workers_common.async_bridge import run_async
from {pkg}.handlers.schemas import XxxPayload, XxxResult

logger = get_logger(__name__)


def handle_xxx_task(self, payload: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    """Celery 同步入口（bind=True 故首参 self）。兼容 payload（旧）/kwargs（推荐）两种风格。"""
    raw = dict(payload) if payload else dict(kwargs)
    logger.info("收到 xxx 任务", operation="{域}.task.received", payload=raw)
    try:
        result = run_async(_async_handle_xxx(raw))          # ✅ run_async，不是 asyncio.run
        logger.info("xxx 任务完成", operation="{域}.task.success", result=result)
        return result
    except Exception as e:
        logger.error("xxx 任务失败", operation="{域}.task.error", error=str(e), payload=raw)
        raise                                                # re-raise 触发 broker 重试


async def _async_handle_xxx(raw: dict[str, Any]) -> dict[str, Any]:
    data = XxxPayload(**raw)                                 # ✅ 入口处 dict→模型（见 §4.2）
    injector = get_injector()
    from {pkg}.app.application.commands.create_xxx import CreateXxxCommand
    command = injector.get(CreateXxxCommand)                 # ✅ 调 command，不写业务
    result = await command.execute(**data.model_dump())
    return XxxResult(xxx_id=result.xxx.id).model_dump()      # ✅ 返回模型 .model_dump()，不手拼 dict
```

> ⚠️ **模板偏差声明**：`pingpong-worker` 的 `handlers/pp_demo.py` 已改为用 `run_async`（async 调度正确），但仍手拼 dict 返回、未走 `handlers/schemas.py`——**返回部分不得仿写**。新 handler 必须用 `run_async` + `schemas.py` 模型（`.model_dump()` 返回）。正确形态参考 `echo_task_handler.py` 与 `beat_demo_handler.py`（均 `from workers_common.async_bridge import run_async`，见 §4.5）。

### 4.2 Payload 与返回值的数据载体（必须模型化）

worker 入口的 payload 由消息队列传入，**入口处必然是 `dict`**（队列协议决定）。约束如下：

- handler 接收 `dict payload`（或 `**kwargs`）——这是队列边界，等价 service 的 HTTP body 解析。
- **复杂 payload 必须在 handler 内转成 Pydantic 模型再传给 application**（`handlers/schemas.py` 定义入站模型，如 `XxxPayload`），禁止把裸 dict 传进 application。
- handler 的返回值**必须先构造 Pydantic 结果模型**（`handlers/schemas.py` 的 `XxxResult`）**再 `.model_dump()`** 序列化进 result backend，**禁止手拼 `{"id": ...}`**。
- `handlers/schemas.py` 是 worker **必备文件**（等价 service 的 `api/v1/schemas/`），承载所有 handler 的入站 payload 模型与出站 result 模型。

```python
# handlers/schemas.py  —— handler 专用 payload/result 模型
from pydantic import BaseModel, Field


class XxxPayload(BaseModel):
    """xxx 任务入站 payload 校验模型"""
    user_id: str = Field(..., description="目标用户")
    content: str = Field(..., min_length=1, max_length=1000)


class XxxResult(BaseModel):
    """xxx 任务返回结果（序列化进 result backend）"""
    xxx_id: str
    delivered: bool
```

> 一句话：**裸 dict 只允许在"队列协议边界"瞬存在（payload 入的瞬间、`.model_dump()` 出的瞬间）；handler 内部立即转模型，application 及以下全程是 Entity/VO/Schema。**
>
> ⚠️ **模板偏差声明**：`pp_demo.py` 手拼 dict 返回、且无 `handlers/schemas.py`——**待修脏模板**，不得仿写。

### 4.3 注册表（`handlers/registry.py`）与 topic / 队列命名

集中把 topic 映射到 handler。新增 handler = 新增处理器文件 + 在此注册一行。import 在函数体内（与 modules.py 同理，防循环）。

```python
# handlers/registry.py
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from workers_common.broker.base import BaseBroker

# topic 用模块级常量声明，便于 config 路由与 registry 共用、避免拼写漂移
SEND_EMAIL_TOPIC = "notify_worker.send_email"           # 消费型：{pkg}.{task}
CLEANUP_BEAT_TOPIC = "notify_worker.daily_cleanup"      # Beat 型：{pkg}.{task}


def register_all_handlers(broker: "BaseBroker") -> None:
    # 消费型任务
    from {pkg}.handlers.send_email_handler import handle_send_email
    broker.register_handler(SEND_EMAIL_TOPIC, handle_send_email)

    # Beat 定时任务（如有）
    from {pkg}.handlers.daily_cleanup_handler import handle_daily_cleanup
    broker.register_handler(CLEANUP_BEAT_TOPIC, handle_daily_cleanup)
```

#### 4.3.1 topic 命名格式（两段点分 snake，强制）

**所有 topic 统一为两段 `{pkg}.{task}`**，点分，每段 snake_case（`_` 连词，不用 `-`）：

| 段 | 取值 | 示例 |
|---|---|---|
| 第 1 段 `{pkg}` | worker 包名 = `{worker_name}_worker` | `notify_worker`、`content_ops_worker` |
| 第 2 段 `{task}` | 任务名 snake_case | `send_email`、`process_video`、`daily_cleanup` |

| 任务类型 | topic 格式 | 示例 |
|---|---|---|
| 消费型（队列消息触发） | `{pkg}.{task}` | `notify_worker.send_email`、`content_ops_worker.process_video` |
| Beat 定时（Celery Beat 调度） | `{pkg}.{task}` | `notify_worker.daily_cleanup`、`content_ops_worker.outbox_scan` |

- **两段，不带 `tasks` 固定段**。消费型与 Beat 型用同一格式，靠 `CELERY_BEAT_SCHEDULE` 区分（Beat 任务才进 schedule），不靠 topic 形态区分。
- topic 全小写，词用 `_`，段用 `.`。`send_email`✅ 不是 `sendEmail`/`send-email`。
- **投递方 `send_task(topic)` 与 registry 注册的字符串必须逐字一致**——用模块级常量（`SEND_EMAIL_TOPIC`）而非裸字符串，杜绝拼写漂移。

> ⚠️ **模板偏差声明**：`pingpong-worker` 的 `pp_demo.py` 注册了 `pingpong_worker.pingpong`（三段、带 `tasks`）——这是**待修脏模板**，**不得仿写**。新建 topic 一律两段 `{pkg}.{task}`（与 `content_ops_worker.process_video` 等生产用法一致）。

#### 4.3.2 队列命名格式（三段点分 snake，强制）

`CELERY_TASK_ROUTES` 里每个 topic 路由到的 **queue 名统一为三段 `{pkg}.{domain}.{subdomain}`**，点分，每段 snake_case：

| 段 | 取值 | 示例 |
|---|---|---|
| 第 1 段 `{pkg}` | worker 包名 | `content_ops_worker` |
| 第 2 段 `{domain}` | 业务域 | `video`、`scene`、`callback` |
| 第 3 段 `{subdomain}` | 子域/动作 | `processing`、`task`、`notify` |

```python
# foundation/config.py —— 队列路由，queue 用三段 {pkg}.{domain}.{sub}
NTF_CELERY_TASK_ROUTES: dict = {
    "notify_worker.send_email":      {"queue": "notify_worker.email.send"},
    "notify_worker.send_sms":        {"queue": "notify_worker.sms.send"},
    "notify_worker.daily_cleanup":   {"queue": "notify_worker.maintenance.cleanup"},
}
```

- 三段点分 snake，全小写。`content_ops_worker.video.processing`✅ 不是 `content_ops_worker_video_processing`/`video-processing`。
- 第 2、3 段按业务域细分，让聚合 broker 能**按队列 fork 隔离**（慢队列不饿死快队列，见开发指南 §14.4）。
- 多个 topic 可路由到同一队列（如多个 Beat 扫描任务共用 `content_ops_worker.callback_notify` 队列）。
- `CELERY_TASK_QUEUES` 留空时，聚合 broker 会从 `CELERY_TASK_ROUTES` 的 queue 值自动派生队列列表。

> ⚠️ **模板偏差声明**：`pingpong-worker` 的队列名只用 `pingpong`（一段，无 pkg 前缀）——**待修脏模板**，不得仿写。新建队列一律三段 `{pkg}.{domain}.{sub}`（与 `content_ops_worker.video.processing` 等生产用法一致）。

### 4.4 Handlers 禁止事项

- ❌ 在 handler 里写业务逻辑、直接操作 DB/Redis、直接 import infrastructure 实现或 ORM Model。
- ❌ 在 handler 里直接 `httpx` 调外部（走 clients）。
- ❌ application 方法把"队列 dict"当参数直接消费（复杂结构应先转模型）。
- ❌ 新增 handler 忘记在 `registry.py` 注册。
- ❌ **用 `asyncio.run()` 调度异步**（必须 `run_async`，见 §4.1）。
- ❌ **handler 手拼 dict 返回**（必须 `XxxResult(...).model_dump()`，见 §4.2）。

### 4.5 Beat 定时任务 handler（第二类入口）

除"队列消费"外，worker 还有 **Beat 定时任务**入口：由 Celery Beat 按计划调度，**无 payload 入参**（签名 `def handle_xxx(self, **kwargs)`），用于周期批处理（清理、扫描、聚合等）。

**多节点幂等**：worker-in-one 部署多实例时，Beat 会在每个节点触发。必须用 **Redis 分布式锁**保证同一时刻只有一个节点执行。锁的实现位置与模板（照搬 `beat_demo_handler.py`）：

- 锁放 **handler 入口**（不放 application）：用 `get_injector().get(RedisManager)` 取 Redis，`set(_LOCK_KEY, owner, nx=True, ex=_LOCK_TTL)`。
- 锁 Key 命名：`{prefix}:{域}:leader`（如 `ntf:cleanup:leader`），TTL 覆盖单次执行最大耗时（防死锁）。
- 抢锁失败 → 返回 `{"skipped": True, "lock_owner": ...}`，不报错。
- 抢锁成功 → 执行业务；异常 → 记录后返回 `{"error": ...}`（不 re-raise，Beat 任务无需重试）。

```python
# handlers/{域}_beat_handler.py  —— Beat handler 标准形态（照搬 beat_demo_handler.py 改名）
import uuid
from typing import Any

from {pkg}.foundation.container import get_injector
from {pkg}.foundation.logging import get_logger
from workers_common.async_bridge import run_async as _run_async

logger = get_logger(__name__)

_LOCK_KEY = "{prefix}:{域}:leader"      # ← 改本 worker 前缀 + 业务域
_LOCK_TTL = 120                          # 2 分钟，覆盖单次执行最大耗时


def handle_{域}_beat(self, **kwargs: Any) -> dict[str, Any]:
    """Celery Beat 定时任务（无 payload）。多节点靠 Redis 锁幂等。"""
    acquired, lock_owner = _run_async(_try_acquire_lock())
    if not acquired:
        logger.debug("Beat {域} skipped: another node holds the lock", lock_owner=lock_owner)
        return {"skipped": True, "lock_owner": lock_owner}

    logger.info("Beat {域} lock acquired", lock_owner=lock_owner, operation="{pkg}.{域}_beat.lock_acquired")
    try:
        result = _run_async(_async_execute(lock_owner))
        logger.info("Beat {域} completed", operation="{pkg}.{域}_beat.done", **result)
        return result
    except Exception as exc:
        logger.error("Beat {域} failed", exc=exc, operation="{pkg}.{域}_beat.error")
        return {"skipped": False, "lock_owner": lock_owner, "error": str(exc)}


async def _try_acquire_lock() -> tuple[bool, str]:
    from workers_common.redis import RedisManager
    rm = get_injector().get(RedisManager)
    lock_owner = str(uuid.uuid4())[:8]
    acquired = await rm.set(_LOCK_KEY, lock_owner, nx=True, ex=_LOCK_TTL)
    if acquired:
        return True, lock_owner
    current = await rm.get(_LOCK_KEY)
    return False, current or "unknown"


async def _async_execute(lock_owner: str) -> dict[str, Any]:
    """实际业务：通过 injector 取 application service 执行。"""
    injector = get_injector()
    from {pkg}.app.application.services.{域}_service import {Pascal}Service
    service = injector.get({Pascal}Service)
    return await service.do_scheduled_work()
```

Beat 调度配置（在 `foundation/config.py` 的 `{PREFIX}_CELERY_BEAT_SCHEDULE`）见 §6、§18。新增 Beat handler 流程：① 复制 `beat_demo_handler.py` 改名；② 改 `_LOCK_KEY`/`_LOCK_TTL`/业务；③ config 加 Beat schedule 条目 + 路由；④ `registry.py` 注册。

---

## 5. main 启动与 DI 装配（`main.py`）

worker 的 `main.py` 承担 service 中"app 工厂 + 容器装配"的角色：

- `setup()`：装配 `DatabaseManager` / `RedisManager`（支持 worker-in-one 复用 `SharedResources`）、构建 `Injector`（`BuiltinModule + ClientsModule + DomainModule + ApplicationModule + InfrastructureModule`）、`set_injector`，返回 `cleaner`。
- `run_worker()`：`configure_logging` → `asyncio.run(setup(...))` → 前缀覆盖 `CELERY_*` → `BrokerManager().register("celery", settings)` → `manager.start_all()`。
- **`async_bridge` 生命周期钩子**：`setup()` 内调用 `install_shutdown_hook()`（幂等），把 `dispose_thread_loop` 挂到 Celery `worker_shutdown` 信号 + `atexit`，把 `reset_thread_local` 挂到 `worker_process_init`（prefork 二次 fork 后清掉继承的父线程 loop/资源缓存，`--pool=threads` 下为 no-op）。`cleaner` 里再 `dispose_thread_loop()` 释放主线程 thread-local 资源。handler 层无需关心这些钩子，只需 `from workers_common.async_bridge import run_async`。
- **thread-local 资源装配（`--pool=threads` 适配）**：`DatabaseManager`/`RedisManager` 不再绑成进程级单例——单例 manager 的连接池会绑定到首个工作线程的 loop，其余线程复用即跨 loop 崩。`setup()` 用 `workers_common.thread_resources` 的 provider（`get_or_create_db_manager` / `get_or_create_redis_manager`）按 `scope=None` 绑定，每次 `injector.get` 取**当前工作线程**惰性创建的 manager（池绑本线程 loop）。thread-local 在 prefork 下退化为「每进程一份」，无回归。
- **all-in-one / worker-in-one 复用**：standalone 模式 `install_shutdown_hook()` 在 `setup()` 覆盖；worker-in-one 模式下队列子进程也会再注册一次（幂等）。DB/Redis 一律走 thread-local provider，忽略 `shared_resources` 传入的进程级共享 manager（共享 manager 为 prefork 单例设计，threads 下不安全）。

> DI 容器、`get_injector`/`set_injector`、各层 `modules.py` 注册规则与 service 规范 §6 完全一致。

> ⚠️ **`modules.py` 四条硬约定同样适用 worker**（service §6.1.1）：① import 一律写在 `configure()` 方法体内（防循环导入）；② 绑定统一 `binder.bind(接口, to=实现, scope=None)`；③ `DomainModule.configure` 保持 `pass`；④ 接口→实现绑定只在 `InfrastructureModule`/`ClientsModule`。worker 的 `app/infrastructure/modules.py`、`app/application/modules.py`、`clients/modules.py` 照此结构，不得变形。

> ⚠️ **统一继承 `workers_common`，严禁 import `services_common`**：worker 的 shared 层是 `workers/common`（`workers_common`），不是 `services_common`。`foundation/config.py` 继承 `from workers_common import AppSettings, DatabaseSettings, RedisSettings, WorkersSettings`（见 §6 已给模板）。`workers/` 目录下任何文件出现 `import services_common` 即为不合格。

> ⚠️ **外部服务调用走 `clients/`，不进 `infrastructure/`**（与 service §2.1 同）：worker 调别的 service/第三方用 httpx/SDK，只能在 `clients/{依赖}/remote_api.py`（standalone）或 `local_api.py`（worker-in-one）；`infrastructure/` 只适配本 worker 自己的执行元数据库（`{prefix}_task_execution` 等）。`infrastructure/` 出现 `httpx` 即不合格。

---

## 6. 配置规范（`foundation/config.py`）

worker 配置继承公共配置并叠加 `WorkersSettings`，**不含 HOST/PORT/CORS** 等 Web 字段。

> ⚠️ **关键约定（照抄 pingpong-worker 模板）**：
> - import 来源是 **`workers_common`**（不是 `services_common`）：`from workers_common import AppSettings, DatabaseSettings, RedisSettings, WorkersSettings`。`WorkersSettings` 由 `workers_common` 提供（含全部 `CELERY_*` 默认值），**不要在 worker 本地重新定义它**。
> - worker 用**前缀字段**声明队列路由，名字为 `{PREFIX}_CELERY_*`（如 `NTF_CELERY_TASK_ROUTES`），`run_worker()` 启动时把这些前缀字段**覆盖**到公共 `CELERY_*` 字段再启动 broker（见 §5 `run_worker()`）。
> - `REDIS_PREFIX` 取 `worker_prefix`（如 `ntf`），不要留模板的 `"pipo"`。

```python
# foundation/config.py  —— 以 notify-worker（prefix=ntf）为例
from functools import lru_cache
from pydantic_settings import SettingsConfigDict
from workers_common import AppSettings, DatabaseSettings, RedisSettings, WorkersSettings


class Settings(AppSettings, DatabaseSettings, RedisSettings, WorkersSettings):
    """Notify Worker 配置 - 继承公共配置"""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8",
        case_sensitive=False, extra="allow",
    )

    # ── Broker 专有配置（用 worker 前缀，register 时覆盖 CELERY_*）──
    # 继承 workers_common.WorkersSettings 的全部 CELERY_* 默认值
    # topic 两段 {pkg}.{task}；queue 三段 {pkg}.{domain}.{sub}（见 §4.3）
    NTF_CELERY_TASK_DEFAULT_QUEUE: str = "notify_worker.email.send"
    NTF_CELERY_TASK_ROUTES: dict = {
        "notify_worker.send_email": {"queue": "notify_worker.email.send"},
    }
    NTF_CELERY_TASK_QUEUES: str = "notify_worker.email.send"

    # 任务超时（按任务耗时调，默认偏短）
    CELERY_TASK_TIME_LIMIT: int = 300
    CELERY_TASK_SOFT_TIME_LIMIT: int = 270

    REDIS_PREFIX: str = "ntf"              # ← 本 worker 前缀，不要留 "pipo"

    # 外部服务配置（调别的 service）
    OTHER_SERVICE_URL: str = "http://localhost:8001"


@lru_cache
def get_settings() -> Settings:
    """获取缓存的配置实例"""
    return Settings()
```

- `MODEL` 取值 `standalone` / `worker-in-one`，决定 clients 走 remote 还是 local。
- broker / 中间件相关配置统一收敛在 `workers_common.WorkersSettings`，新增中间件在那加配置段，不在各 worker 重复。
- `CeleryBroker` 通过 `getattr(settings, key, default)` 动态读取配置，各 worker 的前缀字段（`NTF_CELERY_*`）在 `run_worker()` 里覆盖到 `CELERY_*` 后生效。

> ⚠️ **模板偏差声明（两处必改，否则 worker 跑不通）**：
> 1. **`run_worker()` 的前缀覆盖**：模板里是 `_settings.CELERY_TASK_DEFAULT_QUEUE = _settings.PIPO_CELERY_TASK_DEFAULT_QUEUE` 等（`PIPO_` 前缀）。改写时必须把 `PIPO_` 全部换成本 worker 前缀（`NTF_`），并确保 `NTF_CELERY_*` 字段已在 `Settings` 声明。漏改会导致 broker 用空路由/队列名。
> 2. **clients 的 `api_proxy.py` 的 MODEL 比较值**：模板里写 `if setting.MODEL == "all-in-one"`（这是 service 的取值）。worker 的 `MODEL` 取值是 `standalone` / `worker-in-one`，**永远不会等于 `all-in-one`**，照抄会导致 local 模式（worker-in-one）永远走 remote 分支、本地直调失效。改写时必须把 `== "all-in-one"` 改为 `== "worker-in-one"`。

#### 6.1 Beat 调度配置（配合 §4.5）

启用了 Beat 定时任务（§4.5）的 worker，在 `Settings` 加：

```python
NTF_CELERY_BEAT_ENABLE: bool = True
NTF_CELERY_BEAT_SCHEDULE: dict = {
    "daily-cleanup": {
        "task": "notify_worker.daily_cleanup",    # 与 registry 注册的 Beat topic 一致（两段 {pkg}.{task}）
        "schedule": {"crontab": {"minute": 0, "hour": 4}},   # 每日 4 点；或 {"timedelta": {"minutes": 5}}
    },
}
```

`run_worker()` 里同样把 `NTF_CELERY_BEAT_*` 覆盖到 `CELERY_BEAT_*`。`resolve_schedule`（聚合器内部）把 dict 形式转 Celery 的 `timedelta`/`crontab`。详情见开发指南第 18 节。

---

## 7. 共享模块使用

> ⚠️ **铁律：`workers/` 下任何文件都不得 `import services_common`**。worker 的共享层是 `workers/common`（包名 `workers_common`），与 service 的 `services_common` 平行。需要 DB/Redis/日志/配置基类时，一律从 `workers_common` 引入。

- worker 的通用能力（DB/Redis/日志/配置基类/异常/中间件等）统一从 **`workers_common`** 引入，不从 `services_common`。
  - 例：`from workers_common import DatabaseManager, RedisManager`、`from workers_common.logging import Logger, configure_logging`、`from workers_common import AppSettings, DatabaseSettings, RedisSettings, WorkersSettings`。
- worker 间共享逻辑放 `workers/common`（`workers_common`），如 worker 专用 config、resource_keys、shared_resources 等。
- **`workers_common.broker`**：Broker 抽象基类（`BaseBroker`）、工厂（`create_broker`）、管理器（`BrokerManager`）、注册表（`BROKER_REGISTRY`）、实现（`CeleryBroker` 等）。统一在通用层，**各 worker 本地不建 `broker/` 目录**，直接 `from workers_common.broker import BrokerManager`。
- 不要在单个 worker 内重复实现 `workers_common` 已提供的能力。

> 为什么硬性禁止 import `services_common`？因为 `services_common` 可能带 FastAPI/Web 依赖，而 worker 无 HTTP。保持 worker 依赖树干净，且 service/worker 是两条独立部署线。worker 需要 service 能力时走 `clients/` HTTP 调用，不直接 import service 代码。

---

## 8. 命名规范（worker 特有部分）

| 对象 | 规则 | 示例 |
|---|---|---|
| worker 目录 | `{名}-worker`（短横线） | `pingpong-worker` |
| 包名 | `{名}_worker`（下划线） | `pingpong_worker` |
| Broker 实现类 | `{中间件}Broker` | `CeleryBroker` |
| Broker 实现文件 | `{中间件}_broker.py` | `celery_broker.py` |
| Handler 函数 | `handle_{任务}` | `handle_pingpong_task` |
| Handler 异步函数 | `_async_handle_{任务}` | `_async_handle_pingpong` |
| Handler 文件 | `{域}_handler.py` | `notify_handler.py` |
| Topic（注册名） | 两段 `{pkg}.{task}`，点分 snake | `notify_worker.send_email`、`content_ops_worker.process_video` |
| 队列名（queue） | 三段 `{pkg}.{domain}.{sub}`，点分 snake | `notify_worker.email.send`、`content_ops_worker.video.processing` |

> 其余命名（实体/仓储/Model/Command/Query/Service/Client 代理/日志 operation）与 service 规范 §10 一致。

> ℹ️ **Worker 无 HTTP 路由**：worker 不暴露 HTTP，因此**不涉及 service §5.1.1 的 path/tags/聚合 prefix 命名约束**。worker 的命名对象只有 Python 文件/类/函数（snake_case/PascalCase，多词用 `_`，如 `notify_handler.py`、`handle_send_email`）与 Celery topic/queue（点分 snake：topic 两段 `{pkg}.{task}` 如 `notify_worker.send_email`，queue 三段 `{pkg}.{domain}.{sub}` 如 `notify_worker.email.send`，见 §4.3）。不要把 HTTP 路由的 kebab-case 规则套到 worker 的文件名/topic/queue 上。

> ⚠️ **ORM Model 类名必须带服务前缀**（与 service 规范 §5.4 一致）：`{PREFIX_UPPER}{表}Model`（**全大写前缀**）。前缀取 `worker_prefix`（来自 `worker.metadata` 的 `worker_prefix`，等价于 service 的 `service_prefix`）的整体全大写形式。例如 pingpong-worker（`worker_prefix = "pipo"`）的 notification 表 → `PIPONotificationModel`，表名 `pipo_notification`；notify-worker（`worker_prefix = "ntf"`）的 notification 表 → `NTFNotificationModel`，表名 `ntf_notification`。目的：all-in-one / worker-in-one 合并运行时多个服务共享同一 `DeclarativeBase`，类名不带前缀会冲突、前缀风格不统一难以辨识归属。
>
> **仲裁规则**：`PREFIX_UPPER = worker_prefix.upper()`（整体全大写）。`ntf`→`NTF`、`pipo`→`PIPO`、`coo`→`COO`。现存 `pingpong-worker` 模板的 `PingModel`/`PongModel`（无前缀）是**待修脏模板**，**不得仿写**；复刻新 worker 时必须手工改为 `{PREFIX_UPPER}{表}Model`。

---

## 9. 禁止事项（worker 汇总）

**继承 service 全部禁止事项**（裸 dict 契约、同层多类别塞一文件、application 依赖具体实现、domain 依赖框架、repository 返回 ORM Model、同步 DB、忘记 DI 注册等），**外加 worker 特有项**：

1. ❌ 中间件 SDK（celery 等）泄漏到 `handlers/` / `app/` 任意层（只能在 `broker/implementations/` 内）。
2. ❌ handler 写业务逻辑（必须下沉 application）。
3. ❌ application 直接消费队列裸 dict（复杂 payload 先转模型）。
4. ❌ 新增中间件时改 `BaseBroker` 或既有实现（应新增文件 + 注册表）。
5. ❌ 新增 handler 忘记在 `registry.py` 注册。
6. ❌ worker 里出现 HTTP 端口 / FastAPI / 路由相关代码。
7. ❌ worker-in-one 模式下重复创建/关闭已由 `SharedResources` 提供的 DB/Redis。
8. ❌ **`workers/` 下任何文件 `import services_common`**：worker 共享层是 `workers_common`（见 §7）。
9. ❌ **外部服务调用写进 `infrastructure/`**：调别的 service/第三方只能在 `clients/`；`infrastructure/` 只适配本 worker 执行元数据库。`infrastructure/` 出现 `httpx` 即不合格（与 service §2.1 同）。
10. ❌ **`modules.py` 顶层 import 业务类 / 缺 `scope=None` / `DomainModule` 里塞绑定**：照 service §6.1.1 四条硬约定。
11. ❌ **重命名脚手架生成的目录或顶层包**：`generate-worker` 后包名/前缀/import 根已正确，AI 不得改名（见 §0.1）。
12. ❌ **`run_worker()` 里前缀覆盖语句漏改**：`PIPO_CELERY_*` 必须改为本 worker 的 `{PREFIX}_CELERY_*` 覆盖到 `CELERY_*`（见 §5）。
13. ❌ **ORM Model 类名/表名不带 worker 前缀**：`class {PREFIX_UPPER}{表}Model`（全大写前缀）、表名 `{prefix}_{表}`（全小写）（与 service §5.4 同）。
14. ❌ **topic 用三段带 `tasks` 或用 `-`/驼峰**：topic 统一两段 `{pkg}.{task}` 点分 snake（`notify_worker.send_email`），不带 `tasks` 段，不用 `-`/驼峰。见 §4.3.1。
15. ❌ **队列名不三段点分**：queue 统一三段 `{pkg}.{domain}.{sub}` 点分 snake（`content_ops_worker.video.processing`），不用一段、不用 `_` 整体连接、不用 `-`。见 §4.3.2。
16. ❌ **topic 写裸字符串而非常量**：topic 应用模块级常量（`SEND_EMAIL_TOPIC`）声明，registry 与投递方共用，禁止散落裸字符串导致拼写漂移。

---

## 10. 开发流程检查清单（提交前逐条核对）

**入口层（worker 特有）**
- [ ] 新任务有独立 `handlers/{域}_handler.py`，并在 `registry.py` 注册
- [ ] handler 为同步入口 + `run_async`（持久 loop），业务在 `_async_xxx` 内调 application
- [ ] handler 不含业务逻辑、不碰 DB/infrastructure/httpx
- [ ] 复杂 payload 已转 Pydantic 模型再交给 application
- [ ] 新增中间件：新增 `implementations/` 文件 + `BROKER_REGISTRY` 注册，未改既有代码
- [ ] 中间件 SDK 仅在 `broker/implementations/` 内 import
- [ ] **topic 两段 `{pkg}.{task}` 点分 snake**（`notify_worker.send_email`），用模块级常量声明，不带 `tasks` 段（§4.3.1）
- [ ] **队列名三段 `{pkg}.{domain}.{sub}` 点分 snake**（`content_ops_worker.video.processing`），在 `CELERY_TASK_ROUTES` 配（§4.3.2）

**分层（与 service 一致，复用其检查清单）**
- [ ] domain/application/infrastructure/clients 均符合 service 规范
- [ ] **未 `import services_common`**（用 `workers_common`）
- [ ] **外部服务调用在 `clients/`，不在 `infrastructure/`**；二者不互相 import
- [ ] 层间/clients/repository 无裸 dict（队列边界除外）
- [ ] 新增依赖已在对应 `modules.py` 注册，import 在 `configure()` 体内、`scope=None`、`DomainModule` 空（§6.1.1）
- [ ] ORM 类名/表名带 worker 前缀（`NTFNotificationModel` / `ntf_notification`）

**配置与装配**
- [ ] 配置继承 `workers_common.WorkersSettings`，无 Web 字段，import 来自 `workers_common`
- [ ] 前缀字段 `{PREFIX}_CELERY_*` 已在 `run_worker()` 覆盖到 `CELERY_*`；`REDIS_PREFIX` 取本 worker 前缀（非 `pipo`）
- [ ] `MODEL` 区分 standalone/worker-in-one，clients 模式切换正确
- [ ] `setup()` 正确处理 `SharedResources` 复用与 `owns_*` 清理

**命名与清理**
- [ ] 命名按 §0.1 占位符表推导；未重命名脚手架生成的目录/顶层包
- [ ] demo 代码已清理：grep 不到 `pingpong`/`pp_demo`/`PIPO` 残留，删除的类在 `modules.py` 同步移除绑定（§0.2）

---

## 11. 记忆强化

> 🔒 **开始开发 worker 时，立即回忆：**
>
> 1. **worker = service 去掉 HTTP，换成消息队列**：`api/` → `handlers/` + `broker/`，其余层完全照搬 service 规范。
> 2. **broker 统一在 `workers_common.broker`**：`base.py`(ABC) + `factory.py`(注册表) + `implementations/`(实现)，各 worker 的 `broker/` 仅转发。扩展靠注册表，配置靠 `getattr` 动态读取。
> 3. **handler 是入口适配**：同步入口 `run_async`（持久 loop）→ `_async_xxx` → application，不写业务。
> 4. **裸 dict 只活在队列边界**（payload 入 / result 出），进 application 即转 Entity/VO/Schema。
> 5. **数据流**：MQ → broker → handler → application → domain ← infrastructure；clients 被 application 用。

---

*本规范与 `develop/ai-coding-service-app.md` 配套使用：分层细节看 service 规范，入口差异看本规范。验收标准同样是"消除差异"。*

---

## 附录 A：端到端完整示例（一个 `notify` 任务从 0 到 1）

> 本附录展示"新增一个 worker 任务"时**每个文件长什么样、放哪里、怎么串起来**。包名以 `pingpong_worker` 为例。

### A.1 需求

新增一个 `notify` 任务：消息队列投递 `{"user_id": "...", "channel": "sms", "content": "..."}`，worker 消费后落库一条通知记录，并调用外部 account-service 查用户信息。

### A.2 文件清单（新增/修改）

```
handlers/notify_handler.py                          [新增] 任务入口（同步 + run_async）
handlers/registry.py                                [改]   注册 topic → handler
app/application/commands/create_notification.py     [新增] 写用例（逻辑写在此，handler 调它）
app/application/services/notify_service.py          [不建] 本例为单聚合写，归 commands；跨聚合/复用场景才归 service（见 service 规范 §5.2）
app/application/modules.py                           [改]   注册 command（无 service 则不注册 service）
app/domain/entities/notification.py                 [新增] 实体
app/domain/repositories/notification_repository.py  [新增] 仓储接口
app/infrastructure/persistence/models/notification_model.py        [新增] ORM（类名 PIPONotificationModel，表名 pipo_notification）
app/infrastructure/persistence/repositories/sql_notification_repository.py  [新增] 实现
app/infrastructure/modules.py                       [改]   绑定
clients/account_service/...                          [新增] 外部服务（interface/schemas/remote/local/proxy）
clients/modules.py                                  [改]   注册
foundation/config.py                                [改]   外部服务地址 + topic 相关
```

> domain / application / infrastructure / clients 的写法与 service 规范**完全一致**（参见 service 规范附录 A）。本附录只展开 worker 特有的 `handlers/` 与 payload 处理。

### A.3 Payload 模型（队列边界转模型，避免 application 吃裸 dict）

```python
# handlers/schemas.py  （handler 专用的入站 payload 模型，等价 service 的请求 DTO）
from typing import Literal
from pydantic import BaseModel, Field


class NotifyPayload(BaseModel):
    """notify 任务入站 payload 校验模型"""
    user_id: str = Field(..., description="目标用户")
    channel: Literal["sms", "email", "push"] = Field(..., description="通知渠道")
    content: str = Field(..., min_length=1, max_length=1000)


class NotifyResult(BaseModel):
    """notify 任务返回结果（会被序列化进 result backend）"""
    notification_id: str
    delivered: bool
```

### A.4 Handler（入口适配层，等价 service 的 endpoint）

```python
# handlers/notify_handler.py
from typing import Any

from pingpong_worker.foundation.container import get_injector
from pingpong_worker.foundation.logging import get_logger
from workers_common.async_bridge import run_async
from pingpong_worker.handlers.schemas import NotifyPayload, NotifyResult

logger = get_logger(__name__)


def handle_notify_task(self, payload: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    """Celery 同步入口（bind=True 故首参 self）。只做：校验→调度异步→组装结果。"""
    raw = dict(payload) if payload else dict(kwargs)
    logger.info("收到 notify 任务", operation="notify.task.received", payload=raw)
    try:
        result = run_async(_async_handle_notify(raw))     # ✅ run_async（持久 loop），非 asyncio.run
        logger.info("notify 任务完成", operation="notify.task.success", result=result)
        return result
    except Exception as e:
        # 记录后 re-raise，让 broker 感知失败、触发重试
        logger.error("notify 任务失败", operation="notify.task.error", error=str(e), payload=raw)
        raise


async def _async_handle_notify(raw: dict[str, Any]) -> dict[str, Any]:
    """异步业务调度：队列裸 dict → Pydantic 模型 → application。"""
    data = NotifyPayload(**raw)                  # ✅ 队列边界处转模型，禁止把裸 dict 传进 application

    injector = get_injector()
    from pingpong_worker.app.application.commands.create_notification import CreateNotificationCommand
    command = injector.get(CreateNotificationCommand)   # ✅ handler 调 command，逻辑不在 service

    result = await command.execute(
        user_id=data.user_id, channel=data.channel, content=data.content,
    )
    notification = result.notification

    # ✅ 返回值序列化进 result backend，用模型 .model_dump() 而非手拼 dict
    return NotifyResult(
        notification_id=notification.notification_id, delivered=True,
    ).model_dump()
```

> **关键点**：`dict payload`（入）与 `dict 返回`（出）**只允许出现在 handler 这一层**——它是队列协议边界。进入 `notify_service` 后全程是 Entity；返回也是先构造 `NotifyResult` 模型再 `.model_dump()`，而不是手写 `{"notification_id": ...}`。

### A.5 注册到 registry

```python
# handlers/registry.py
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from workers_common.broker.base import BaseBroker


def register_all_handlers(broker: "BaseBroker") -> None:
    # 注意：pp_demo 的 topic 是模板偏差（三段带 tasks），新 handler 不仿写
    from pingpong_worker.handlers.pp_demo import handle_pingpong_task
    broker.register_handler("pingpong_worker.pingpong", handle_pingpong_task)   # 改写为两段

    # 新增 notify（两段 {pkg}.{task}）：
    from pingpong_worker.handlers.notify_handler import handle_notify_task
    broker.register_handler("pingpong_worker.notify", handle_notify_task)
```

### A.6 Application / Domain（与 service 一致，此处给关键骨架）

> ⚠️ 应用层职责按 service 规范 §5.2 决策树定位：本例「发通知」是**单聚合写**，归 `commands/`，逻辑写在 `execute`——所以 handler 调的是 `CreateNotificationCommand` 而非 `NotifyService`。若该流程跨聚合或被多用例复用，则归 `services/`（非备选）。

```python
# app/application/commands/create_notification.py
from dataclasses import dataclass
from injector import inject

from pingpong_worker.app.domain.entities.notification import Notification
from pingpong_worker.app.domain.repositories.notification_repository import NotificationRepository
from pingpong_worker.clients.account_service.interface import AccountService


@dataclass
class CreateNotificationResult:
    notification: Notification


class CreateNotificationCommand:
    @inject
    def __init__(self, repo: NotificationRepository, account: AccountService):
        self.repo = repo                    # ✅ 直接注入仓储接口
        self.account = account              # ✅ 外部服务走 clients 接口

    async def execute(self, user_id: str, channel: str, content: str) -> CreateNotificationResult:
        user = await self.account.get_user_by_id(user_id)   # clients 返回 schema，非裸 dict
        notification = Notification.create(user_id=user.user_id, channel=channel, content=content)
        saved = await self.repo.create(notification)
        return CreateNotificationResult(notification=saved)
```

> 当「发通知」跨多个聚合事务，或被多个 command（如 `CreateNotificationCommand` 和 `BatchNotifyCommand`）复用时，就把编排归到 `services/notify_service.py`，由 command 委托调用——这是 service 的本职，不是"勉强才建"。单聚合写则留在 command。

### A.7 任务的完整数据流转

```
MQ 投递 {"user_id":"u1","channel":"sms","content":"hi"}
   │
   ▼  broker 消费 topic=pingpong_worker.notify
handlers/notify_handler.handle_notify_task   (同步入口)
   │  run_async(_async_handle_notify(raw))
   ▼
_async_handle_notify
   │  NotifyPayload(**payload)                 ← 队列边界：dict → 模型
   │  command.execute(...)
   ▼
application/create_notification.CreateNotificationCommand
   │  account.get_user_by_id(...)  → UserInfo(schema)   ← clients 返回模型
   │  Notification.create(...)                          ← domain 实体
   │  repo.create(notification)                         ← 注入接口
   ▼
infrastructure/sql_notification_repository
   │  _to_model → PIPONotificationModel → 落库
   ▼
返回 Notification(Entity) ──► NotifyResult(模型).model_dump() ──► result backend
```

---

## 附录 B：新增一种中间件（以 RabbitMQ 为例，演示开闭原则）

> 需求：除 Celery 外新增 RabbitMQ 支持。**不改任何既有文件的内部逻辑**，只"新增实现文件 + 注册表加一行 + 配置加一段"。

### B.1 新增实现文件

> 实现文件放在 `workers_common/broker/implementations/`，因为 broker 抽象层是所有 worker 共享的。

```python
# workers/common/src/workers_common/broker/implementations/rabbitmq_broker.py
from typing import Any, Callable

import pika   # ← 中间件 SDK 只允许在本实现文件内 import，禁止泄漏到 handler/app

from workers_common.broker.base import BaseBroker


class RabbitMQBroker(BaseBroker):
    """RabbitMQ 消息队列实现"""

    def __init__(self, settings):
        self.settings = settings
        self._handlers: dict[str, Callable] = {}
        self._conn: "pika.BlockingConnection | None" = None

    def register_handler(self, topic: str, handler: Callable) -> None:
        self._handlers[topic] = handler

    def start(self) -> None:
        from {pkg}.handlers import register_all_handlers
        register_all_handlers(self)                 # ← 与 Celery 实现一致：先注册再消费

        self._conn = pika.BlockingConnection(pika.URLParameters(self.settings.BROKER_URL))
        channel = self._conn.channel()
        for topic, handler in self._handlers.items():
            channel.queue_declare(queue=topic, durable=True)
            channel.basic_consume(
                queue=topic,
                on_message_callback=self._wrap(handler),
                auto_ack=False,
            )
        channel.start_consuming()

    def _wrap(self, handler: Callable):
        import json

        def _on_message(ch, method, properties, body):
            payload = json.loads(body)
            try:
                handler(None, payload)              # handler 签名 (self, payload)，独立运行时 self=None
                ch.basic_ack(delivery_tag=method.delivery_tag)
            except Exception:
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

        return _on_message

    def stop(self) -> None:
        if self._conn and not self._conn.is_closed:
            self._conn.close()

    def send_task(self, topic: str, payload: dict[str, Any], **kwargs) -> Any:
        import json
        conn = pika.BlockingConnection(pika.URLParameters(self.settings.BROKER_URL))
        channel = conn.channel()
        channel.queue_declare(queue=topic, durable=True)
        channel.basic_publish(exchange="", routing_key=topic, body=json.dumps(payload))
        conn.close()
        return topic
```

### B.2 注册表加一行（`workers_common/broker/factory.py`，唯一需要"改"的既有文件）

```python
# workers/common/src/workers_common/broker/factory.py
BROKER_REGISTRY: dict[str, str] = {
    "celery": "workers_common.broker.implementations.celery_broker.CeleryBroker",
    "rabbitmq": "workers_common.broker.implementations.rabbitmq_broker.RabbitMQBroker",  # ← 新增
}
```

### B.3 配置加一段 + 注册

```python
# foundation/config.py 中覆盖 WorkersSettings 字段
class Settings(AppSettings, RedisSettings, WorkersSettings):
    BROKER_URL: str = "amqp://guest:guest@localhost:5672/"
    # ... RabbitMQ 专属配置
```

```python
# main.py 中显式注册
manager = BrokerManager()
manager.register("rabbitmq", RabbitMQBroker(_settings))
manager.start_all()
```

> 切换中间件只需在 `main.py` 中替换注册的 broker 实现类。配置层不需要 `BROKER_TYPE`——直接在代码中指定要用的 broker。

---

## 附录 C：从外部投递任务（send_task）

worker 自身只消费；**投递方**（service 或另一个 worker）投递任务到 worker 消费的 topic。

**Service 侧投递**（生产做法）：service 用 `services_common.task_publisher.TaskPublisherManager`（封装 `celery.send_task`），不直接碰 worker 的 broker：

```python
# service 的 application/infrastructure 层
@inject
class MyDispatcher:
    def __init__(self, manager: TaskPublisherManager):
        self._manager = manager

    def dispatch_notify(self, payload: dict):
        self._manager.send(
            broker_name="celery",
            topic="notify_worker.send_email",          # 两段 {pkg}.{task}，与 worker registry 注册一致
            payload=payload,
            queue="notify_worker.email.send",          # 三段 {pkg}.{domain}.{sub}，与 worker CELERY_TASK_ROUTES 一致
        )
```

**Worker 侧自分发子任务**（worker 既是 consumer 又是 producer）：在 worker 的 `infrastructure/` 写轻量 dispatcher，用 Celery `current_app.send_task(...)` 投到某队列，由本 worker 消费。

```python
# 投递要点
# 1. topic 必须与 worker registry.py 注册的字符串逐字一致
# 2. payload 用 kwargs 风格（send_task(..., kwargs={...})），worker handler 用 **kwargs 收
# 3. queue 与 worker 的 CELERY_TASK_ROUTES 中该 topic 的 queue 一致
# 4. payload 必须可 JSON 序列化，复杂对象先 .model_dump()
```

> ⚠️ Worker **不得 import `services_common`**（含 task_publisher）。service 投递任务走 `services_common`；worker 自分发走 `workers_common.broker` 或 Celery 原生 `current_app.send_task`。两端各自用各自的共享层。

---

## 附录 D：易错对照速查（worker 特有，❌ → ✅）

| 场景 | ❌ 错误 | ✅ 正确 |
|---|---|---|
| handler 调用 application | `service.send(**payload)`（裸 dict 展开） | `data = NotifyPayload(**payload)` 后传字段 |
| handler 返回 | `return {"id": n.id}`（手拼） | `return NotifyResult(...).model_dump()` |
| 业务逻辑位置 | 写在 `handle_notify_task` 里 | 下沉到 `commands/`/`queries/` 的 `execute` |
| 用例归属 | handler 调 `NotifyService`，逻辑全在 service | 单聚合写调 `CreateNotificationCommand`；跨聚合/复用才归 service（见 service 规范 §5.2 决策树） |
| 异步调度 | handler 内直接 `await ...` 或 `asyncio.run()` | 同步入口用 `run_async(_async_xxx())`（持久 loop，§4.1） |
| 失败处理 | `except: pass` 吞异常 | 记录日志后 `raise`，让 broker 重试 |
| 中间件 SDK | `import celery` 出现在 handler/app | SDK 只在 `workers_common/broker/implementations/` 内 |
| 新增中间件 | 改 `BaseBroker` 或既有实现加 if 分支 | 新增实现文件到 `workers_common/broker/implementations/` + `BROKER_REGISTRY` 加一行 |
| 注册遗漏 | 写了 handler 没进 `registry.py` | `broker.register_handler(topic, fn)` |
| topic 命名 | `"notify"` / `"NotifyTask"` / `带 tasks 三段` | 两段 `{pkg}.{task}`：`"notify_worker.send_email"` |
| 队列命名 | `"notify"` 单段 / 用 `-` | 三段 `{pkg}.{domain}.{sub}`：`"notify_worker.email.send"` |
| 配置 | worker 里写 `PORT` / FastAPI | 只有 `WorkersSettings` + 公共配置，无 Web 字段 |
| 资源复用 | worker-in-one 下重复建 DB/Redis | 用 `SharedResources` + `owns_*` 判定 |
| clients import | `from {pkg}.clients.x import XProxy` | `from {pkg}.clients.x.api_proxy import XProxy`（完整路径） |

---

*分层细节查 service 规范，入口与中间件差异查本规范。两份配套，验收标准都是"消除差异"。*
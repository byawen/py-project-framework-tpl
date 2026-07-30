# Service 开发指南（从 0 到 1 到部署）

> 面向新成员的端到端实战手册。读完本文你应当能够：独立创建一个新服务、在四层 DDD 架构中实现一个完整的业务用例、接入外部服务、运行/测试/迁移，并了解它如何被部署。
>
> 本文是 README 的细化版，与 `develop/ai-coding-service-app.md` 互补：后者是“约束规范”（给 AI / Code Review 用，强调红线），本文是“上手教程”（给人用，强调流程）。规范里只讲结论的地方，这里讲为什么、怎么落地。

---

## 目录

1. [概念全景：Service 是什么](#1-概念全景service-是什么)
2. [环境准备](#2-环境准备)
3. [从一个新服务开始：0 到 1](#3-从一个新服务开始0-到-1)
4. [目录结构即契约](#4-目录结构即契约)
5. [四层 DDD 架构与依赖方向](#5-四层-ddd-架构与依赖方向)
6. [四种数据载体（DTO / Entity / Model / Client Schema）](#6-四种数据载体dto--entity--model--client-schema)
7. [foundation：引导层](#7-foundation引导层)
8. [domain 领域层：纯业务](#8-domain-领域层纯业务)
9. [infrastructure 基础设施层：适配器](#9-infrastructure-基础设施层适配器)
10. [application 应用层：CQRS 与用例编排](#10-application-应用层cqrs-与用例编排)
11. [api 层：HTTP 入口](#11-api-层http-入口)
12. [依赖注入（injector）全链路](#12-依赖注入injector全链路)
13. [clients：外部服务接入](#13-clients外部服务接入)
14. [services_common：共享库能给你什么](#14-services_common共享库能给你什么)
15. [biz_code：统一业务码](#15-biz_code统一业务码)
16. [配置与环境变量](#16-配置与环境变量)
17. [数据库与 Alembic 迁移](#17-数据库与-alembic-迁移)
18. [运行模式：Standalone vs All-in-One](#18-运行模式standalone-vs-all-in-one)
19. [日志、中间件、异常处理](#19-日志中间件异常处理)
20. [测试](#20-测试)
21. [编码规范与提交前检查清单](#21-编码规范与提交前检查清单)
22. [从开发到部署](#22-从开发到部署)
23. [常见坑与排错](#23-常见坑与排错)
24. [完整示例：实现一个 Article 资源](#24-完整示例实现一个-article-资源)
25. [附录：命令速查表](#25-附录命令速查表)

---

## 1. 概念全景：Service 是什么

本仓库有两类可部署组件：

| 类型 | 目录 | 特征 | 示例 |
|---|---|---|---|
| **Service** | `services/*-service/` | 有 HTTP 端口、FastAPI + uvicorn，对外提供 API | pingpong-service（模板） |
| **Worker** | `workers/*-worker/` | 无 HTTP 端口，消费消息队列（Celery over Redis），做异步/后台任务 | pingpong-worker（模板） |

> Worker 的开发请看姊妹篇 `develop/worker-development-guide.md`。本文只讲 Service。

一个 Service 的运行单元长这样：

```
HTTP 请求 → FastAPI 中间件链 → API 层(端点)
                                  ↓ Depends
                              Application 层(Command/Query/Service)
                                  ↓ 注入
                              Domain 层(Entity/VO/Repository接口)  ← 契约
                                  ↑ 实现
                              Infrastructure 层(SQL Repository/Redis/...)
                                  ↓
                              PostgreSQL / Redis / 外部服务
```

关键设计点（先记住，后面会展开）：

- **严格分层**：`api → application → domain ← infrastructure`，单向依赖，domain 不依赖任何框架。
- **CQRS by convention**：写操作放 `application/commands/`，读操作放 `application/queries/`，编排多聚合/多步骤放 `application/services/`。
- **依赖注入用 `injector`**：每个层有一个 `modules.py` 声明绑定，全局 `Injector` 在 `main.py` 装配，通过 `foundation/container.py` 暴露 `get_injector()`。
- **`services_common` 是共享地基**：统一响应、异常、配置、DB/Redis 管理、中间件、biz_code 工具都在里面，Service 自己只写业务。
- **`clients/` 接外部服务**：每个外部依赖一个目录，interface + local/remote/proxy + schemas 五件套，通过 `settings.MODEL` 自动切换 all-in-one 本地调用 / standalone HTTP 调用。
- **统一业务码 biz_code**：8 位编码 `1 SS DDD EEE`，贯穿异常 → 响应，便于跨服务定位。

---

## 2. 环境准备

### 2.1 必备工具

| 工具 | 版本 | 用途 |
|---|---|---|
| Python | ≥ 3.12 | 运行时（根 `pyproject.toml` 要求 `>=3.12`） |
| uv | 最新 | 包管理器（不用 pip/poetry） |
| Docker + Compose | 最新 | 本地起 PostgreSQL / Redis 等依赖 |
| Make | 任意 | 跑 Makefile 目标 |

> ⚠️ 注意：README 里写“Python 3.10+”，但根 `pyproject.toml` 与各服务都要求 `>=3.12`，ruff/mypy 也锁定 `py312`。**以 3.12 为准**。

### 2.2 首次初始化

```bash
# 1. 克隆仓库
git clone <repo-url> 01-claw-project && cd 01-claw-project

# 2. 创建虚拟环境并安装 uv
python3.12 -m venv .venv
source .venv/bin/activate
pip install uv

# 3. 安装全部 workspace 成员（services/common 是地基，会被各服务以 workspace 方式依赖）
make install          # 等价于在每个 service 里 uv sync

# 4. 起本地依赖（PostgreSQL + Redis）- 可选
make compose-up       # 实际读 deploy/local/docker-compose.yml
```

### 2.3 包管理：uv workspace 机制（必懂）

本仓库是一个 **uv workspace**。根 `pyproject.toml` 里：

```toml
[tool.uv.workspace]
members = [
    "services/common",
    "services/pingpong-service",
    # ... 其他服务由脚手架按需追加
    "all-in-one",
    # ...
]

[tool.uv.sources]
services-common = { workspace = true }
# 每个服务也各自声明：services-common = { workspace = true }
```

含义：

- `services/common` 是包名为 `services-common`、导入名 `services_common` 的**内部共享库**，不发布到 PyPI。
- 每个服务的 `pyproject.toml` 里 `dependencies = [..., "services-common"]`，并通过 `[tool.uv.sources] services-common = { workspace = true }` 声明从 workspace 取，而不是从 PyPI。
- 新增服务时，必须把它注册进根 `pyproject.toml` 的三处：`[project].dependencies`、`[tool.uv.workspace].members`、`[tool.uv.sources]`。**好消息：脚手架脚本会自动改这三处**（见第 3 节）。

### 2.4 认识 Makefile

根 Makefile 动态发现 `services/*/Makefile`，分三类目标：

- **批量**：`make install / lint / test / migrate / docker-build / health`（遍历所有服务）
- **单服务**：`make install-service SERVICE=xxx / dev SERVICE=xxx / test-service SERVICE=xxx` 等
- **聚合**：`make all-in-one`（把所有服务跑进一个进程）

> 完整命令见文末[附录](#25-附录命令速查表)。

---

## 3. 从一个新服务开始：0 到 1

本仓库**不用 cookiecutter**，而是用脚本克隆 `services/pingpong-service`（它既是参考实现，也是模板），再做有序字符串替换重命名。脚本同时会改根 `pyproject.toml`。

### 3.1 脚手架命令

```bash
make generate-service SERVICE=<kebab名> SHORT_PREFIX=<2-10位前缀> SERVICE_CODE=<1-89的整数> PORT=<端口>
# 例：
make generate-service SERVICE=my-app SHORT_PREFIX=ma SERVICE_CODE=20 PORT=8005
```

参数规则（脚本会校验）：

| 参数 | 规则                                             | 示例 |
|---|------------------------------------------------|---|
| `SERVICE` | kebab-case，仅字母/数字/连字符，不能数字开头，不需要 “-service” 后缀 | `my-app` |
| `SHORT_PREFIX` | 仅字母/数字，长度 2–10，不能数字开头                          | `ma` |
| `SERVICE_CODE` | 整数 1–89，**全局唯一**（0 留给 pingpong 模板/common 兜底）   | `20` |
| `PORT` | 1–65535，可选，默认 8000                             | `8005` |

> 选 `SERVICE_CODE` 前先看“已分配码表”（脚本报错也会提示冲突）。`SERVICE_CODE` 取值 1–89 且全局唯一（0 留给 pingpong 模板/common 占位），前缀同理要先查，避免和别的服务撞。

### 3.2 生成后的完整流程

```bash
# 1. 生成，注意不需要携带“-service”后缀，例如下面 my-app 最终生成出来的是 my-app-service
make generate-service SERVICE=my-app SHORT_PREFIX=ma SERVICE_CODE=20 PORT=8005

# 2. 进 venv 安装新 workspace 成员
source .venv/bin/activate
make install-service SERVICE=my-app-service    # 内部 uv sync --all-extras --all-packages

# 3. 起本地 DB（可选，若没起）
make compose-up

# 4. 跑迁移（模板自带 alembic，会用 <prefix>_ 前缀过滤本服务的表）
make migrate-service SERVICE=my-app-service

# 5. 启动开发
make dev SERVICE=my-app-service
# → PYTHONPATH=src uvicorn my_app_service.main:app --port 8005 --host 0.0.0.0 --reload

# 6. 验证
curl http://localhost:8005/health
# 打开 http://localhost:8005/docs （DEBUG=true 时才有 Swagger）
```

到这一步你已经有一个能跑的空壳服务，它继承了 pingpong 的 demo 端点（已被重命名为你的前缀）。接下来就是把 demo 换成真实业务。

### 3.3 （可选）接入 All-in-One

如果希望这个服务也能跑进聚合进程 `make all-in-one`，需在 `all-in-one/` 与 `deploy/` 做 7 处注册（根 pyproject、all-in-one pyproject、config.py 多继承 + 访问器、services.py 加载块、Dockerfile COPY + install、migrate.sh、本服务 router 前缀）。

完整步骤与原理见 [第 18 节](#18-运行模式standalone-vs-all-in-one)（特别是 §18.7 接入清单与 §18.2 装配流程）。核心两步预览：

1. `all-in-one/src/all_in_one/config.py`：把新服务 `Settings` 加进 `Settings(...)` 的 MRO，并加 `get_<service>_settings()` 访问器（设 `MODEL="all-in-one"`、`APP_NAME` 加后缀、`REDIS_PREFIX`）。
2. `all-in-one/src/all_in_one/services.py`：加一段加载块
   ```python
   from my_app_service.main import setup as my_app_setup
   service_settings = _settings.get_my_app_settings()
   cleaner = await my_app_setup(app, service_settings, logger, shared_resources=shared_resources)
   ```


```python
# all-in-one/src/all_in_one/services.py 的 services_registry()
async def services_registry(app: FastAPI, _settings: Settings, logger: Logger):
    try:
        from xxx_service.main import setup as xxx_setup
        service_settings = _settings.get_xxx_settings()
        cleaner = await xxx_setup(app, service_settings, logger, shared_resources=shared_resources)
        cleaner_list.append(cleaner)
        _services_registry[service_settings.APP_NAME] = {"enabled": True}
    except Exception as e:
        logger.warning(f">>>>>>> Failed to load xxx-service exception: {e}")
        logger.warning(f">>>>>>> Failed to load xxx-service stack: {traceback.format_exc()}")
```

```python
# all-in-one/src/all_in_one/config.py 的 Settings 多继承 + 访问器
class Settings(AllInOneSettings, ..., XxxxSettings):
    def get_xxx_settings(self):
        """获取 Xxx 服务配置"""
        config_dict = vars(self).copy()
        config_dict.update({
            "MODEL": "all-in-one",
            "APP_NAME": self.APP_NAME + "-xxx",
            "REDIS_PREFIX": "xxx",
        })
        return XxxxSettings(**config_dict)
```

---

## 4. 目录结构即契约

> 原则：**目录即契约**。除下列清单外，不得在服务根目录新增顶层目录。

生成后的服务骨架（以 `my-app-service` 为例）：

```
my-app-service/
├── .env / env.example            # 本地配置 / 配置模板
├── Dockerfile                    # 镜像构建（注意从仓库根构建）
├── Makefile                      # 本服务的 install/dev/test/migrate/lint/docker-build
├── README.md                     # 本服务说明
├── alembic.ini                   # 迁移配置（version_table 用前缀，避免多服务共用 DB 互踩）
├── pyproject.toml                # 依赖、ruff/mypy 配置
├── service.metadata              # 4 字段 JSON，仅工具读取（运行时不读）
├── alembic/
│   ├── env.py                    # 用 SERVICE_TABLE_PREFIXES 过滤本服务表
│   └── script.py.mako
├── tests/                        # 测试
└── src/
    └── my_app_service/      # 导入根（PYTHONPATH=src）
        ├── __init__.py
        ├── main.py               # FastAPI app 工厂 + lifespan + DI 装配
        ├── foundation/           # 引导层（非 DDD 层）：config/container/logging/biz_code/exception_handlers
        ├── clients/              # 外部服务客户端（消费者侧）
        ├── pkg/                  # 通用工具（sdk/utils）
        └── app/                  # DDD 四层
            ├── api/              # API 层
            ├── application/      # 应用层
            ├── domain/           # 领域层
            └── infrastructure/   # 基础设施层
```

### 各顶层包职责一句话

| 包 | 一句话职责 | 能 import 什么 |
|---|---|---|
| `foundation/` | 引导与横切：配置、DI 容器、日志、biz_code、异常处理器 | 任意 |
| `clients/` | 外部服务适配器（local/remote/proxy + interface + schemas） | services_common、domain 接口、httpx |
| `pkg/` | 纯工具函数，无业务 | 标准库 |
| `app/api/` | HTTP 入口：参数校验、鉴权、调 application、组装 `DataResponse` | application、schemas、services_common.response |
| `app/application/` | 用例编排，CQRS：commands/queries/services | domain 接口、clients 接口、services_common |
| `app/domain/` | 纯业务：Entity/VO/Repository 接口/Domain Service | 仅自身 + services_common 基类型 |
| `app/infrastructure/` | 适配器实现：SQL Repository、Redis Cache、ORM Model | domain 接口、sqlalchemy/redis/httpx、ORM Model |

---

## 5. 四层 DDD 架构与依赖方向

这是本仓库最重要的红线。**依赖只能从左到右、向下**：

```
api ──▶ application ──▶ domain ◀── infrastructure
                                   （实现 domain 接口）
clients ──▶（被 application 使用）
```

完整依赖矩阵（✅ 可 import / ❌ 禁止）：

| 调用方 ↓ \ 被调方 → | api | application | domain | infrastructure | clients | ORM Model |
|---|---|---|---|---|---|---|
| **api** | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **application** | ❌ | ✅ | ✅(接口) | ❌(具体实现) | ✅(接口) | ❌ |
| **domain** | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| **infrastructure** | ❌ | ❌ | ✅(接口) | ✅ | ❌ | ✅ |
| **clients** | ❌ | ❌ | ❌(一般) | ❌ | ✅ | ❌ |

几条最容易踩的红线：

- ❌ **api 不得 import infrastructure 或 ORM Model**。API 只能见到 DTO（schemas）。
- ❌ **application 不得 import 具体基础设施实现**（如 `SQLPingRepository`、`httpx`），只能依赖 domain 抽象接口（`PingRepository`）和 clients 接口。
- ❌ **domain 不得 import 任何框架**：不能出现 `sqlalchemy`、`redis`、`httpx`、`fastapi`，也不能有 ORM Model。
- ❌ **Repository 接口返回/接收的只能是 Entity，不能是 ORM Model**。ORM Model 永远不跨出 infrastructure 边界。

> 为什么这么严？因为这样/domain 层可以被独立测试、可以替换持久化实现、可以在 all-in-one 与 standalone 间无差别运行。任何一条红线被破，这套价值就崩了。

---

## 6. 四种数据载体（DTO / Entity / Model / Client Schema）

每层有且只有一种属于自己的数据载体，**不得跨界混用**：

| 载体 | 归属层 | 类型 | 边界 | 示例 |
|---|---|---|---|---|
| **DTO** | api | pydantic BaseModel | 只在 api 层流动；请求/响应 | `PingResponse`、`PongRequest` |
| **Entity** | domain | pydantic BaseModel（`from_attributes=True`） | domain ↔ application；Repository 接口的契约 | `Ping`、`Pong` |
| **ORM Model** | infrastructure | `services_common.database.BaseModel` 子类 | 只在 infrastructure 内；不跨边界 | `PIPOPingModel`（表 `pipo_ping`） |
| **Client Schema** | clients | pydantic BaseModel | clients ↔ application；外部调用的入参/出参 | `UserInfo` |

转换规则：

- `ORM Model ↔ Entity`：在 infrastructure 的 Repository 里写 `_to_entity()` / `_to_model()` 私有方法。
- `Entity ↔ DTO`：在 api 端点里手动组装（`PingResponse(message=result.message, ...)`）。
- `Client Schema ↔ Entity`：在 application 层决定如何把外部数据映射进领域。

明确禁止的写法：

```python
# ❌ ORM Model 跨层
async def get(self) ->PIPOPingModel: ...          # domain/application 里返回 ORM

# ❌ dict 当契约
def get_user(self) -> dict: ...                # 裸 dict 跨边界

# ❌ DTO 进 domain
class Ping(Entity):
    dto: PingResponse                          # domain 反向依赖 api
```

---

## 7. foundation：引导层

`foundation/` 不是 DDD 层，是横切的引导代码，都是基础实现。每个服务都有这五个文件：

### 7.1 `config.py` — 配置

```python
from functools import lru_cache
from pydantic_settings import SettingsConfigDict
from services_common import AppSettings, DatabaseSettings, RedisSettings

class Settings(AppSettings, DatabaseSettings, RedisSettings):
    """Article Gen Service 配置 - 继承公共配置"""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8",
        case_sensitive=False, extra="allow",
    )

    # 服务专有配置
    REDIS_PREFIX: str = "ag"
    OTHER_SERVICE_URL: str = "http://localhost:8001"

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

要点：
- 通过**多继承** `services_common` 的配置 Mixin 拿到 `APP_NAME/DEBUG/MODEL`、`DATABASE_URL/DB_POOL_SIZE`、`REDIS_URL` 等公共字段，自己只加服务专有字段。
- `extra="allow"`：允许 `.env` 里有未声明字段（便于全量 .env 复用）。
- `get_settings()` 用 `@lru_cache` 全进程单例。
- 外部服务 URL 命名约定：`{SERVICE}_SERVICE_URL`（如 `OTHER_SERVICE_URL`），自定义字段要带本服务前缀。

### 7.2 `container.py` — 全局 Injector 访问器

```python
from typing import Optional
from injector import Injector

_injector: Optional[Injector] = None

def set_injector(injector: Injector) -> None:
    global _injector
    _injector = injector

def get_injector() -> Injector:
    if _injector is None:
        raise RuntimeError("Injector not initialized. Call this after startup.")
    return _injector
```

这就是“全局 DI 容器”。`main.py` 启动时 `set_injector(...)`，其他地方（FastAPI 的 `Depends` 工厂、测试）用 `get_injector().get(SomeType)` 取实例。

### 7.3 `logging.py` — 日志封装

薄封装 `services_common.logging.Logger`，提供 `LogManager`（可注入）和模块级 `get_logger()` 便捷函数（给非 DI 调用点用，如模块顶部 `logger = get_logger(__name__)`）。

### 7.4 `biz_code.py` — 业务码枚举

```python
from services_common import BizCategory, make_biz_code
from services_common.biz_code import _BIZ_CODE_BASE  # 实际用 make_biz_code

SERVICE_CODE = 20  # 由 generate-service 写入

class BizCode(IntEnum):
    """业务码 - 每个成员必须有中文注释"""
    SUCCESS = make_biz_code(SERVICE_CODE, BizCategory.SUCCESS, 0)
    ARTICLE_NOT_FOUND = make_biz_code(SERVICE_CODE, BizCategory.NOT_FOUND, 1)  # 文章不存在
    ARTICLE_ALREADY_EXISTS = make_biz_code(SERVICE_CODE, BizCategory.CONFLICT, 2)  # 文章已存在
    # ...
```

详见 [第 15 节](#15-biz_code统一业务码)。

### 7.5 `exception_handlers.py` — 异常处理器注册

```python
def register_exception_handlers(app: FastAPI):
    register_base_exception_handlers(app)  # 来自 services_common
```

一行调用，把 `services_common` 提供的统一异常处理器挂上（把带 `biz_code` 的 domain/application 异常翻译成统一 `DataResponse`）。

---

## 8. domain 领域层：纯业务

domain 是最纯的层：**只有业务概念，没有任何技术细节**。包结构：

```
app/domain/
├── entities/          # 聚合根 / 实体（pydantic BaseModel）
├── value_objects/     # 值对象
├── repositories/      # Repository 接口（ABC）
├── caches/            # Cache 接口（ABC）
├── common/exceptions.py  # 领域异常（绑定 BizCode）
├── services/          # （可选）纯领域服务，无 IO
└── modules.py         # DomainModule（DI，通常为空）
```

### 8.1 Entity

```python
# app/domain/entities/ping.py
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from .value_objects.ping_message import PingMessage  # 仅依赖 VO

class Ping(BaseModel):
    """Ping 聚合根"""
    model_config = ConfigDict(from_attributes=True)  # 让 ORM Model 能映射进来

    ping_id: str
    message: PingMessage              # 持有值对象，保证不变量
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def update_message(self, new_message: str) -> None:
        """领域方法 - 封装业务规则"""
        self.message = PingMessage(new_message)   # 通过 VO 校验不变量
```

要点：
- 用 pydantic `BaseModel`，配 `from_attributes=True` 以便 ORM → Entity。
- 持有**值对象**而非裸字符串，把不变量校验下沉到 VO。
- 领域方法（`update_message`）封装业务规则，不做事 IO。

### 8.2 Value Object

```python
# app/domain/value_objects/ping_message.py
class PingMessage:
    """值对象 - 在边界处校验不变量"""
    def __init__(self, raw: str):
        if not raw or len(raw) > 1000:
            raise ValueError("message 长度需在 1-1000")
        self._value = raw

    def __eq__(self, other): return isinstance(other, PingMessage) and self._value == other._value
    def __hash__(self): return hash(self._value)
    def __str__(self): return self._value
```

### 8.3 Repository 接口

```python
# app/domain/repositories/ping_repository.py
from abc import ABC, abstractmethod
from typing import Optional
from ..entities.ping import Ping

class PingRepository(ABC):
    """仓储接口 - 由 infrastructure 实现"""
    @abstractmethod
    async def get_by_id(self, ping_id: str) -> Optional[Ping]: ...
    @abstractmethod
    async def create(self, ping: Ping) -> Ping: ...
    @abstractmethod
    async def update(self, ping: Ping) -> Ping: ...
    @abstractmethod
    async def delete(self, ping_id: str) -> None: ...
```

注意：接口方法的入参/返回**只能是 `Ping`（Entity）**，绝不能是 ORM Model。

### 8.4 领域异常

```python
# app/domain/common/exceptions.py
from services_common import BaseDomainException
from pingpong_service.foundation.biz_code import BizCode

class PaPNotFoundException(BaseDomainException):
    """PingPong 记录不存在"""
    def __init__(self, p_id: str = None):
        message = f"pap not found: {p_id}" if p_id else "pap not found"
        super().__init__(message, code="PAP_NOT_FOUND", biz_code=BizCode.PAP_NOT_FOUND)
```

每个领域异常**必须绑定一个 `BizCode` 成员**，这样统一异常处理器能在响应里带上精确业务码。

### 8.5 `modules.py`

```python
class DomainModule(Module):
    def configure(self, binder: Binder):
        pass  # domain 没有具体实现要绑，留空占位
```

通常为空。domain 的接口→实现绑定发生在 infrastructure 的 `modules.py`。

---

## 9. infrastructure 基础设施层：适配器

infrastructure 是**唯一**允许接触数据库/缓存/外部 SDK 的层。它实现 domain 的接口。

```
app/infrastructure/
├── persistence/
│   ├── models/           # ORM Model（SQLAlchemy）
│   └── repositories/     # SQL Repository 实现
├── caches/               # Cache 实现（Redis）
├── security/             # 密码等
└── modules.py            # InfrastructureModule（接口→实现绑定）
```

### 9.1 ORM Model

```python
# app/infrastructure/persistence/models/ping_model.py
from sqlalchemy import String, DateTime
from services_common import BaseModel  # 共享声明基类

class PIPOPingModel(BaseModel):
    __tablename__ = "pipo_ping"     # ⚠️ 必须带 service_prefix 前缀（全小写）！

    ping_id = Column(String, primary_key=True)
    message = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False)
```

⚠️ **两条硬规则**（all-in-one 多服务共用一个 DB 时必须遵守）：

1. **表名必须带前缀**：`{service_prefix}_{表}`（全小写，如 `pipo_ping`、`acc_user`）。否则多服务共用库会撞表。
2. **ORM 类名必须带前缀**：`{SERVICE_PREFIX_UPPER}{表}Model`（**整体全大写前缀**，如 `PIPOPingModel`、`ACCUserModel`），与全小写表名前缀来自同一个 `service_prefix`、仅大小写不同。否则多服务共用同一 `DeclarativeBase` 会类名冲突。详见 `ai-coding-service-app.md` §5.4。

### 9.2 SQL Repository 实现

```python
# app/infrastructure/persistence/repositories/sql_ping_repository.py
from injector import inject
from services_common import DatabaseManager
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pingpong_service.app.domain.entities.ping import Ping
from pingpong_service.app.domain.repositories.ping_repository import PingRepository
from pingpong_service.app.infrastructure.persistence.models.ping_model import PIPOPingModel
from pingpong_service.foundation.logging import LogManager
from services_common.logging import Logger

class SQLPingRepository(PingRepository):
    @inject
    def __init__(self, dm: DatabaseManager, log_manager: LogManager):
        self._dm = dm
        self._logger: Logger = log_manager.get_logger(__name__)

    async def get_by_id(self, ping_id: str) -> Ping | None:
        async with self._dm.session() as session:
            stmt = select(PIPOPingModel).where(PIPOPingModel.ping_id == ping_id)
            model = (await session.execute(stmt)).scalar_one_or_none()
            return self._to_entity(model) if model else None

    async def create(self, ping: Ping) -> Ping:
        async with self._dm.session() as session:
            model = self._to_model(ping)
            session.add(model)
            await session.commit()
            await session.refresh(model)
            return self._to_entity(model)

    # ── ORM ↔ Entity 转换（私有方法）──
    def _to_entity(self, model: PIPOPingModel) -> Ping:
        return Ping(
            ping_id=model.ping_id,
            message=model.message,         # 值对象从 str 构造
            created_at=model.created_at,
        )

    def _to_model(self, entity: Ping) -> PIPOPingModel:
        return PIPOPingModel(
            ping_id=entity.ping_id,
            message=str(entity.message),
            created_at=entity.created_at,
        )
```

要点：
- `@inject __init__` 注入 `DatabaseManager`、`LogManager`。
- **每个操作一个 `async with self.dm.session() as session:`**，DB 操作必须 async。
- `_to_entity` / `_to_model` 负责载体转换。**返回值永远是 Entity，绝不返回 ORM Model。**
- 日志用结构化 kwarg：`self._logger.info("查询 ping", operation="pingpong.ping.get_by_id", ping_id=ping_id)`。

### 9.3 Redis Cache 实现

```python
# app/infrastructure/caches/pp_redis_cache.py
@inject
class PPRedisCache(PPCache):     # PPCache 是 domain 里的 ABC
    def __init__(self, rm: RedisManager, setting: Settings):
        self._rm = rm
        self._prefix = setting.REDIS_PREFIX   # 用配置里的前缀拼 key
    # ... 实现接口方法，key 都加前缀
```

### 9.4 `modules.py` — 接口→实现绑定

```python
# app/infrastructure/modules.py
class InfrastructureModule(Module):
    def configure(self, binder: Binder):
        binder.bind(PPCache, to=PPRedisCache, scope=None)
        binder.bind(PingRepository, to=SQLPingRepository, scope=None)
        binder.bind(PongRepository, to=SQLPongRepository, scope=None)
```

**接口在 domain，实现在 infrastructure，绑定关系声明在这里。** 这是依赖反转的关键。

---

## 10. application 应用层：CQRS 与用例编排

application 层编排用例、依赖 domain 接口与 clients 接口，**不碰**具体实现/ORM/httpx。

```
app/application/
├── commands/        # 写操作（Command 模式）
├── queries/         # 读操作（Query 模式）
├── services/        # 跨聚合/多步骤编排（Application Service）
├── common/exception.py  # 应用层异常（绑定 BizCode）
└── modules.py       # ApplicationModule
```

### 10.1 CQRS 决策树（关键！）

接到一个用例，先问这几个问题决定放哪：

```
是否纯读（无副作用）？
├─ 是 → queries/，写一个 XxxQuery.execute()
└─ 否（有写）→
     是否只操作单个聚合？
     ├─ 是 → commands/，写一个 XxxCommand.execute()，业务逻辑放 execute 内
     └─ 否（跨聚合 / 多步骤 / 多个仓储协调 / 需要事务）→
          services/，写一个 XxxService，内部组合多个 command/repo
```

两条常见反模式（必须避免）：

- ❌ 单聚合写操作硬抽一个空壳 Service（command 只是转发）：直接放 command。
- ❌ 跨聚合逻辑塞进一个 command：拆出来放 service。

### 10.2 Command（写）

```python
# app/application/commands/create_pong.py
from dataclasses import dataclass
from typing import Optional
from injector import inject

from pingpong_service.app.domain.entities.ping import Pong
from pingpong_service.app.domain.repositories.pong_repository import PongRepository
from pingpong_service.app.domain.value_objects.pong_data import PongData
from pingpong_service.foundation.logging import get_logger

logger = get_logger(__name__)

@dataclass
class PongCommandResult:
    """命令返回值（dataclass，非 dict）"""
    data: str
    pong: Optional[Pong] = None

class PongCommand:
    """创建 Pong 命令处理器"""
    @inject
    def __init__(self, pong_repository: PongRepository):
        self.pong_repository = pong_repository     # 注入接口，不是具体实现

    async def execute(self, data: str) -> PongCommandResult:
        logger.info("创建 pong 开始", operation="pingpong.pong.create.start", input_data=data)
        pong_data = PongData(data)                 # 构造 VO，校验不变量
        pong = Pong(data=pong_data)                # 构造 Entity
        saved = await self.pong_repository.create(pong)   # 调接口
        logger.info("创建 pong 成功", operation="pingpong.pong.create.success",
                    pong_id=saved.pong_id)
        return PongCommandResult(data=data, pong=saved)
```

要点：
- Command 是一个**类**，构造器 `@inject` 注入依赖，业务逻辑在 `execute()`。
- 返回值用 **dataclass**（`PongCommandResult`），不用 dict。
- 入参可以是基本类型或 DTO，**不直接接收 ORM**。
- 日志带 `operation=...` 结构化字段。

> 注：模板里的 `PongCommand` 调用了 `pong_repository.save()`，而 `PongRepository` 定义的是 `create()`——这是模板的占位 stub。真实实现请用 `create()`。

### 10.3 Query（读）

```python
# app/application/queries/get_ping.py
@inject
class PingQuery:
    def __init__(
        self,
        db: AsyncSession,
        redis: Redis,
        ping_repo: PingRepository,
        log_manager: LogManager,
        github_client: GithubOauthAPIClient,      # 外部 client 也能注入
        other_service: OtherServiceAPIProxy,
    ):
        self.db = db
        self.redis = redis
        self.ping_repo = ping_repo
        self.logger = log_manager.get_logger(__name__)
        self.github_client = github_client
        self.other_service = other_service

    async def execute(self) -> PingQueryResult:
        self.logger.info("执行 Ping 查询", operation="pingpong.ping.query.start")
        ping_id = generate_id()                    # services_common.utils
        result = await self.github_client.oauth_request()       # 调外部
        result2 = await self.other_service.get_user_by_id("awen")
        ping = Ping(ping_id=ping_id, message="ping, " + str(result) + " - " + str(result2))
        return PingQueryResult(message=str(ping), ping=ping)
```

Query 可以注入 `AsyncSession`/`Redis` 做直接读（读侧允许适度绕过 Repository 以优化查询）。但**写侧必须走 Repository**。

### 10.4 Application Service（跨聚合编排）

当一个用例需要协调多个 Repository、需要事务边界、或会被多个 Command 复用时，放 `services/`：

```python
# app/application/services/pp_service.py
@inject
class PPService:
    def __init__(self, ping_repo: PingRepository, pong_repo: PongRepository, dm: DatabaseManager):
        self.ping_repo = ping_repo
        self.pong_repo = pong_repo
        self.dm = dm

    async def ping_and_pong(self, message: str, data: str) -> tuple[Ping, Pong]:
        async with self.dm.transaction():          # 事务边界
            ping = await self.ping_repo.create(Ping(...))
            pong = await self.pong_repo.create(Pong(...))
            return ping, pong
```

### 10.5 `modules.py`

```python
class ApplicationModule(Module):
    def configure(self, binder: Binder):
        binder.bind(PongCommand, to=PongCommand, scope=None)
        binder.bind(PingQuery, to=PingQuery, scope=None)
        binder.bind(PPService, to=PPService, scope=None)
```

> **没有 MediatR 式的 dispatcher 注册表**。`injector` 本身就是注册表：在 `modules.py` 写一行 `bind` 就算注册。端点用 `Depends` 工厂从 injector 取实例。新增用例 = 新建文件 + 加一行 bind。

---

## 11. api 层：HTTP 入口

```
app/api/
└── v1/
    ├── router.py           # api_router = APIRouter(prefix="/v1/<service>")
    ├── common/deps.py      # 依赖工厂（鉴权等）
    ├── endpoints/          # 一个资源一个端点文件
    └── schemas/            # DTO（请求/响应）
```

### 11.1 router

```python
# app/api/v1/router.py
from fastapi import APIRouter
from .endpoints.pp_demo import router as pp_router

api_router = APIRouter(prefix="/v1/pingpong")
api_router.include_router(pp_router)
```

注意：`/v1` 前缀在 router 上，`main.py` 又把 `api_router` 挂在 `/api` 下，最终路径是 `/api/v1/pingpong/...`。新版本加 `v2/` 目录。

### 11.2 schemas（DTO）

```python
# app/api/v1/schemas/ping_pong.py
from pydantic import BaseModel
from services_common import DataResponse

class PingResponse(BaseModel):
    message: str
    ping_id: str | None = None
    created_at: datetime | None = None

class PingDataResponse(DataResponse[PingResponse]):
    pass
```

DTO 只在 api 层流动，**不进 domain/infrastructure**。

### 11.3 endpoint

```python
# app/api/v1/endpoints/pp_demo.py
from fastapi import APIRouter, Depends
from pingpong_service.foundation.container import get_injector
from services_common import success, DataResponse

router = APIRouter(prefix="/ping-pong", tags=["ping-pong"])

def get_ping_query() -> PingQuery:           # Depends 工厂
    return get_injector().get(PingQuery)

@router.get("/ping", response_model=DataResponse[PingDataResponse])
async def ping(query: PingQuery = Depends(get_ping_query)) -> DataResponse[PingDataResponse]:
    result = await query.execute()
    ping_data = PingResponse(message=result.message, ping_id=result.ping.ping_id)
    return success(data=ping_data, message="Ping successful")
```

api 层**只做四件事**：

1. 参数校验（FastAPI 自动 + pydantic）
2. 鉴权（`Depends`）
3. 调 application（query/command/service）
4. 组装 `DataResponse` 返回（用 `services_common.response.success/created/...`）

**不得在端点里写业务逻辑、不得直接调 Repository、不得 import infrastructure。**

### 11.4 路由命名规范（kebab-case，禁 `_`）

HTTP 路由所有面向 URL / OpenAPI 的标识统一用 **kebab-case（`-`）**，禁止 `_`。这是高频踩坑点：Python 文件名必须用 `_`（`api_keys.py`），AI 经常顺手把路由 path 也写成 `_`（`/api_keys`）——错。

| 对象 | 用什么 | ✅ | ❌ |
|---|---|---|---|
| HTTP path（`@router.get`、`APIRouter(prefix=)`） | kebab | `/api-keys/{key_id}`、`/user-profile` | `/api_keys/{key_id}` |
| `tags`（OpenAPI 分组） | kebab 全小写英文 | `tags=["api-keys"]` | `tags=["API Keys"]`、`tags=["用量操作"]`、`tags=["api_keys"]` |
| 聚合 router prefix | `/v1/{kebab服务名}` | `/v1/content-quality` | `/v1/content_quality` |
| 路径参数名 / `name` / `operation_id` | snake（Python 标识符） | `/{user_id}`、`name="get_user"` | `/{user-id}` |
| 端点文件名 | snake（Python 文件） | `api_keys.py` | ~~`api-keys.py`~~ |

口诀：**文件 snake，路由 kebab；name 是 Python 标识符故 snake。**

```python
# 文件 app/api/v1/endpoints/api_keys.py（snake）
router = APIRouter(prefix="/api-keys", tags=["api-keys"])    # path/tags kebab

@router.get("/{key_id}", name="get_api_key")                 # 路径参数 key_id 是 snake
async def get_api_key(key_id: str, ...): ...

@router.post("", name="create_api_key")                      # 集合用空串，不重复 prefix
async def create_api_key(...): ...
```

> 现存服务 tags 混乱（`API Keys` 带空格、`用量操作`/`订单` 中文、`api_keys` 下划线）是历史遗留，不要照抄。新建端点一律 `tags=["kebab-case"]` 全小写英文。详见 AI 规范 `ai-coding-service-app.md §5.1.1`。

---

## 12. 依赖注入（injector）全链路

把前面各层的 `modules.py` 串起来的是 `main.py` 的 `setup()`：

```python
# src/my_app_service/main.py（简化）
async def setup(_app, _settings, logger, api_prefix="/api",
                shared_resources: SharedResources | None = None):
    _app.include_router(api_router, prefix=api_prefix)

    # DB / Redis（all-in-one 模式复用 shared_resources）
    _db_manager = shared_resources.get_db() if shared_resources else None \
        or DatabaseManager(database_url=_settings.DATABASE_URL, ...)
    _redis_manager = shared_resources.get_redis() if shared_resources else None \
        or RedisManager(redis_url=_settings.REDIS_URL, ...)

    class BuiltinModule(Module):
        def configure(self, binder):
            binder.bind(Settings, to=lambda: _settings, scope=None)
            binder.bind(RedisManager, to=lambda: _redis_manager, scope=None)
            binder.bind(DatabaseManager, to=lambda: _db_manager, scope=None)
            binder.bind(AsyncEngine, to=lambda: _db_manager.engine, scope=None)
            binder.bind(AsyncSession, to=lambda: _db_manager.session_maker, scope=None)
            binder.bind(LogManager, to=LogManager, scope=None)

    _injector = Injector([
        BuiltinModule,            # 基础单例
        ClientsModule,            # 外部客户端
        DomainModule,             # 通常空
        ApplicationModule,        # Command/Query/Service
        InfrastructureModule,     # 接口→实现
    ])
    set_injector(_injector)
    # 返回 cleaner 关闭资源
```

---

## 13. clients：外部服务接入

每个外部依赖在 `clients/<dependency>/` 下，遵循**五件套**（内部姊妹服务）或**简化版**（第三方）。

### 13.1 完整五件套（内部服务）

```
clients/other_service/
├── interface.py     # ABC 契约
├── schemas.py       # Client Schema（pydantic）
├── local_api.py     # all-in-one 实现（进程内调用）
├── remote_api.py    # standalone 实现（httpx）
└── api_proxy.py     # 按 settings.MODEL 选 local/remote
```

**interface.py** — 契约，整个服务只依赖它：

```python
class UserService(ABC):
    @abstractmethod
    async def get_user_by_id(self, user_id: str) -> UserInfo: ...
```

**schemas.py** — 调用出入参（返回 pydantic，绝不返回裸 dict）：

```python
class UserInfo(BaseModel):
    id: str
    name: str
    email: str | None = None
```

**remote_api.py** — standalone 模式，httpx：

```python
class RemoteUserService(UserService):
    def __init__(self, base_url: str):
        self.client = httpx.AsyncClient(base_url=base_url, timeout=10.0)

    async def get_user_by_id(self, user_id: str) -> UserInfo:
        resp = await self.client.get(f"/users/{user_id}")
        resp.raise_for_status()
        return UserInfo(**resp.json())
```

**local_api.py** — all-in-one 模式，进程内直连（通过 injector 取姊妹服务的 application service）：

```python
class LocalUserService(UserService):
    @property
    def local_service(self):
        if self._local_service is None:
            from pingpong_service.foundation.container import get_injector
            from pingpong_service.app.application.services import PPService
            self._local_service = get_injector().get(PPService)
        return self._local_service
    # ...
```

**api_proxy.py** — 策略选择器：

```python
class OtherServiceAPIProxy(UserService):
    @inject
    def __init__(self, setting: Settings):
        if setting.MODEL == "all-in-one":
            from .local_api import LocalUserService
            self.proxy = LocalUserService()
        else:
            from .remote_api import RemoteUserService
            self.proxy = RemoteUserService(base_url=setting.OTHER_SERVICE_URL)

    async def get_user_by_id(self, user_id: str):
        return await self.proxy.get_user_by_id(user_id)
```

**modules.py** — 绑定接口→Proxy：

```python
class ClientsModule(Module):
    def configure(self, binder):
        binder.bind(GithubOauthAPIClient, to=GithubOauthAPIClient, scope=None)
        binder.bind(OtherServiceAPIProxy, to=OtherServiceAPIProxy, scope=None)
```

实际项目里两种绑定风格：

- **第三方服务**（如模板的 `clients/github/`，只有 remote 无需 local）：`bind(SomeClient, to=SomeClient)` —— 直接绑具体类，无需 local/proxy。
- **内部姊妹服务**（如模板的 `clients/other_service/`，需 local+remote 切换）：`bind(SomeService, to=SomeServiceAPIProxy)` —— 绑 Proxy，让它运行时按 `MODEL` 选 local/remote。

### 13.2 消费客户端

在 application 层构造器声明即可注入：

```python
@inject
class PingQuery:
    def __init__(self, ..., github_client: GithubOauthAPIClient,
                 other_service: OtherServiceAPIProxy):
        self.github_client = github_client
        self.other_service = other_service
```

### 13.3 约定与禁止

- ✅ 一律用 `httpx.AsyncClient`（不用 requests/aiohttp）。
- ✅ 每次调用带 `timeout`（如 `timeout=10.0`）。
- ✅ 认证手动加 header（`Authorization: Bearer <token>`）。
- ✅ 返回 pydantic Client Schema，不返回裸 dict。
- ✅ import 用完整模块路径，不依赖 `__init__.py` 导出。
- ❌ `app/` 里不得直接 `import httpx` —— HTTP 调用只能在 `clients/`。
- ❌ 不得跳过 interface 直接用 remote/local。
- ❌ 不得返回裸 dict 跨边界。

### 13.4 模板范例（供参考）

模板 `services/pingpong-service/` 已经给了两份可直接对照的范例：

- `clients/other_service/remote_api.py`：调一个内部姊妹服务的范例。用 `httpx.AsyncClient(base_url=..., timeout=...)`，POST/GET 到 `/api/v1/<service>/...`，`raise_for_status()`，解包统一响应 `DataResponse` 的 `data` 字段，转成 `UserInfo` 等 Client Schema 返回。配合 `local_api.py` + `api_proxy.py` 实现按 `MODEL` 切换。
- `clients/github/oauth.py`：调一个第三方外部服务的范例（简化版，只有 `api_proxy` 一个文件，无 local/remote 切换）。展示了 `@inject` 注入 `Settings` + `LogManager`、用 client schema 返回、结构化日志的写法。

接入真正的外部服务时，照这两份结构改即可（内部服务抄 `other_service/` 五件套，第三方抄 `github/` 简化版）。

---

## 14. services_common：共享库能给你什么

`services/common`（包名 `services-common`，导入 `services_common`）是所有服务的地基。无需重复造轮子，**优先从这里找**。

### 公共 API（`from services_common import ...`）

| 能力 | 提供物 |
|---|---|
| **响应** | `DataResponse`、`ListResponse`、`PageResponse`、`ErrorResponse` + 构造器 `success/created/list_response/page_response/error/bad_request/unauthorized/forbidden/not_found/conflict` |
| **异常** | `BaseException`、`BaseDomainException`、`BaseApplicationException`、`NotFoundException`、`AlreadyExistsException`、`ValidationException`、`RateLimitException`、`ServiceUnavailableException`、`InvalidCredentialsException` 等 |
| **异常处理器** | `register_base_exception_handlers(app)` |
| **数据库** | `BaseModel`（声明基类）、`DatabaseManager`（连接池 + session/transaction） |
| **Redis** | `RedisManager` |
| **配置** | `AppSettings`、`DatabaseSettings`、`RedisSettings`、`WorkersSettings`、`LLMSettings`、`Settings`、`get_settings` |
| **日志** | `Logger`、`get_logger`、`configure_uvicorn_logging` |
| **中间件** | `RequestIDMiddleware`、`ErrorHandlingMiddleware`、`LoggingMiddleware` |
| **健康检查** | `HealthChecker`、`ServiceHealth`、`HealthCheckResult` |
| **共享资源** | `SharedResources`（all-in-one 共享 DB/Redis） |
| **biz_code** | `BizCategory`、`make_biz_code`、`parse_biz_code` |
| **工具** | `generate_id`、`db_key`、`redis_key`、`mask_sensitive` |

### 统一响应 envelope

所有响应（成功或错误）都长一个样：

```json
{
  "api_version": "v1",
  "result": "success",
  "code": 200,
  "biz_code": 0,
  "message": "Ping successful",
  "timestamp": "...",
  "data": { ... }            // DataResponse 才有
}
```

成功用 `success(data=..., message=...)`，创建用 `created(...)`，分页用 `page_response(items=..., page=..., total=...)`。错误由异常处理器自动生成，**5xx 不向客户端泄露 detail/堆栈**（仅 dev 模式给 422 的 detail）。

> **关于 biz_code 的成功/错误取值**：成功响应的 `biz_code` **固定为 `0`**（"通用成功"占位，不走 8 位结构）——`success()` 默认就是 `0`，别传 `biz_code=BizCode.SUCCESS`。**错误响应**的 `biz_code` 才是 8 位 `1SSDDDEEE`（由异常处理器从 `exc.biz_code` 透传，精确定位"哪个服务 + 哪类错误"）。一句话：成功 = `0`，错误 = 8 位 BizCode。详见 AI 规范 §13.6。

---

---

## 15. biz_code：统一业务码

为了跨服务、跨层定位错误，本仓库用 8 位业务码，公式（见 `services_common.biz_code.make_biz_code`）：

```
biz_code = 10_000_000 + service_code * 1_000_000 + category * 1_000 + seq
            └ 固定基座     └ 服务码 00-89        └ BizCategory 枚举值  └ 业务序号 0-999(0=成功)
```

固定前缀 `10_000_000` 保证始终是 8 位整数（避免 service_code 小时前导零丢失）。

例：假设某服务 `service_code=1`、AUTH(=2) 序号 1 → `10_000_000 + 1*1_000_000 + 2*1_000 + 1` = **`11002001`**。解析反向：`parse_biz_code(11002001)` = `(1, BizCategory.AUTH, 1)`。模板 `pingpong-service` 的 `service_code=0`，其 biz_code 形如 `10_000_000` 起。

### BizCategory 枚举（services_common 提供）

| 值 | 含义 |
|---|---|
| 0 | SUCCESS |
| 1 | VALIDATION |
| 2 | AUTH |
| 3 | NOT_FOUND |
| 4 | CONFLICT |
| 5 | QUOTA |
| 6 | BUSINESS_RULE |
| 7 | EXTERNAL |
| 8 | CONSISTENCY |
| 9 | CONTENT_MEDIA |
| 10 | PAYMENT_TXN |
| 11 | LLM_AI |
| 99 | SYSTEM |

### 在服务里怎么用

1. **`service.metadata` 的 `service_code`** 由 `generate-service` 分配。
2. 脚本同时把它写进 `foundation/biz_code.py` 的 `SERVICE_CODE`。
3. 你在 `foundation/biz_code.py` 声明 `BizCode(IntEnum)`，每个成员用 `make_biz_code(SERVICE_CODE, BizCategory.XXX, 序号)`，**每个成员写中文注释**：

```python
SERVICE_CODE = 20

class BizCode(IntEnum):
    SUCCESS = make_biz_code(SERVICE_CODE, BizCategory.SUCCESS, 0)
    ARTICLE_NOT_FOUND = make_biz_code(SERVICE_CODE, BizCategory.NOT_FOUND, 1)   # 文章不存在
    ARTICLE_ALREADY_EXISTS = make_biz_code(SERVICE_CODE, BizCategory.CONFLICT, 2)  # 文章已存在
    ARTICLE_GEN_FAILED = make_biz_code(SERVICE_CODE, BizCategory.LLM_AI, 3)    # 文章生成失败
```

4. **每个异常必须绑一个 BizCode**（domain/application 异常构造时传 `biz_code=BizCode.XXX`）。
5. 统一异常处理器会把 `biz_code` 放进响应 envelope。

### 约定

- ✅ biz_code 只存在于**响应 envelope**，不进 DTO/Entity/Model。
- ✅ 序号手写，但 `SERVICE_CODE` 与 `BizCategory` 由工具组合，**不要手写裸数字**。
- ❌ 不要在 DTO/Entity 里加 biz_code 字段。

> 模板里有个 `biz-code-test` 端点（`GET /api/v1/<service>/ping-pong/biz-code-test`），主动抛 `RegistrationFailedException` 来验证整条链路：application 异常 → BizCode → 统一处理器 → 响应。可以 curl 验证你的 biz_code 是否贯通。

---

## 16. 配置与环境变量

### 16.1 配置继承结构

你的 `Settings(AppSettings, DatabaseSettings, RedisSettings)` 多继承公共 Mixin。各 Mixin 提供的字段：

- `AppSettings`：`APP_NAME`、`DEBUG`、`ENVIRONMENT`、`MODEL`（`"all-in-one"` / `"standalone"`，**这是 client local/remote 切换开关**）、`CORS_ORIGINS`、`SERVICE_BASE_URL`
- `DatabaseSettings`：`DATABASE_URL`、`DB_POOL_SIZE`、`DB_MAX_OVERFLOW`、`DB_ECHO`
- `RedisSettings`：`REDIS_URL`、`REDIS_MAX_CONNECTIONS`

### 16.2 .env

```
APP_NAME=my-app-service
DEBUG=true
MODEL=standalone

DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/my-app-db
REDIS_URL=redis://localhost:6379/0

REDIS_PREFIX=ag
OTHER_SERVICE_URL=http://localhost:8001
```

- `.env` 是本地配置（被 git 忽略），`env.example` 是模板（提交）。
- `extra="allow"` 允许全量 .env 复用。
- 外部服务 URL 命名：`{SERVICE}_SERVICE_URL`。

---

## 17. 数据库与 Alembic 迁移

### 17.1 为什么用前缀

all-in-one 模式下多个服务共用一个 PostgreSQL。表名带 `service_prefix_` 前缀（`pipo_ping`、`acc_user`）避免撞表。Alembic 也按前缀隔离：

- `alembic.ini` 的 `version_table` = `<prefix>_alembic_version`（每服务独立版本表）
- `alembic/env.py` 用 `SERVICE_TABLE_PREFIXES = "<prefix>_"` 过滤 `include_object`，只迁移本服务的表

### 17.2 迁移命令

```bash
make migrate-service SERVICE=<service>                       # 升级到最新
make migration-create SERVICE=<service> NAME=add_xxx_column  # 自动生成迁移
```

迁移文件落在 `alembic/versions/`。生成后**务必检查** `upgrade()` / `downgrade()` 是否符合预期（自动生成会漏判一些约束）。

### 17.3 写 ORM = 写迁移

新增/改字段流程：改 ORM Model → `make migration-create` → 检查迁移文件 → `make migrate-service` → 测试。

---

## 18. 运行模式：Standalone vs All-in-One

| 模式 | 启动 | 特征 | 何时用 |
|---|---|---|---|
| **Standalone** | `make dev SERVICE=xxx` | 每服务独立进程、独立端口、clients 走 HTTP (`remote_api`) | 单服务开发、独立部署 |
| **All-in-One** | `make all-in-one` | 所有服务跑进一个 FastAPI 进程、共享 DB/Redis 连接池、clients 走进程内 (`local_api`) | 联调、轻量部署 |

### 18.1 All-in-One 是什么

`all-in-one/` 是一个独立包（workspace 成员），它把**所有服务**装进**一个 FastAPI 进程**：

- 一个进程、一个端口（dev 默认 8002，prod 8000）、一套共享的 PostgreSQL/Redis 连接池。
- 每个服务的路由挂在同一个 `app` 上，最终路径 `/api/v1/{service}/...`。
- 服务间互调走**进程内**（`clients/local_api.py`，直接从 injector 取姊妹服务的 application 对象），不走 HTTP。
- 同一份服务业务代码在 standalone 与 all-in-one 下无差别运行——核心收益。

```
                ┌─────────────────────────────────────────────┐
                │         all-in-one FastAPI 进程              │
  HTTP :8002 ──▶│  /api/v1/account/...  (account router)       │
                │  /api/v1/content/... (content router)        │
                │  /api/v1/{service}/... (各服务 router)        │
                │                                              │
                │  共享 DatabaseManager ──▶ PostgreSQL          │
                │  共享 RedisManager   ──▶ Redis               │
                │  各服务 Injector（clients 走 local_api 进程内）│
                └─────────────────────────────────────────────┘
```

### 18.2 装配流程（`all-in-one/src/all_in_one/`）

启动入口 `main.py::create_app()` → `lifespan` → `setup` → `services_registry`（在 `services.py`）。完整顺序：

1. **`create_app()`**：建 FastAPI app，装配中间件链（`ErrorHandlingMiddleware → RequestIDMiddleware → LoggingMiddleware → CORS`，后加先执行）、注册异常处理器、加 `/health` 端点。`DEBUG=true` 才暴露 `/docs`。
2. **`lifespan` 启动**：`configure_logging` → 自建一套 `DatabaseManager`/`RedisManager` 绑进全局 `BuiltinModule` + `Injector`（`set_injector`）→ 调 `setup`。
3. **`services_registry`**（`services.py`，**注意函数名是 `services_registry` 不是 `workers_registry`**）：
   - 建 `SharedResources`，按 `ALL_IN_ONE_SHARE_DB/REDIS`（默认 True）注册共享 `DatabaseManager`/`RedisManager`（key 为 `db:default`/`redis:default`）。
   - **遍历每个服务**：`from <pkg>.main import setup` → `_settings.get_<service>_settings()` 派生子 settings → `await setup(app, service_settings, logger, shared_resources=shared_resources)` → 收集 cleaner → 标记 `enabled`。
   - 加载顺序固定（pingpong → asset → ... → tool，共 19 个）。普通服务失败只 `logger.warning`（跳过继续）；**`data-collector-service` 是必需**，失败 `raise RuntimeError` 终止启动。
4. **各服务 `setup(app, settings, logger, shared_resources=...)`** 做四件事：
   - `_app.include_router(api_router, prefix="/api")`——把本服务路由挂到共享 app。
   - 按 `owns_*` 判断复用 shared DB/Redis 还是自建（见 18.4）。
   - 自建本服务的 `Injector`（5 个 Module）并 `set_injector`。
   - 返回 `cleaner`（仅关闭自己 own 的资源）。
5. **`lifespan` 退出**：关 `lifespan` 自建的 DB/Redis → 调 `services_registry` 返回的 cleaner（各服务 cleaner + `SharedResources.close_all()` 倒序关共享资源）。

> ⚠️ **全局 Injector 被反复覆盖**：`lifespan` 先 `set_injector` 一次，之后每个服务 `setup` 又 `set_injector` 自己的。进程级全局 injector 实际是**最后一个成功 setup 的服务**的。各服务内部注入用的是自己 setup 时建的 injector，所以服务内正常；但**跨服务**用 `get_injector()` 取依赖会拿到最后一个服务的——所以跨服务调用**必须走 `clients/local_api.py`**（它内部用 `get_injector().get(姊妹服务的 Service)`），不要直接共享 injector。

### 18.3 路由如何聚合成 `/api/v1/{service}/...`

all-in-one **不做任何路径重写**。聚合靠两层前缀拼接：

- 每个服务的 `app/api/v1/router.py` 自带 `APIRouter(prefix="/v1/{service}")`（如 account 是 `/v1/account`）。
- 各服务 `setup` 调 `_app.include_router(api_router, prefix="/api")`。

`/api` + `/v1/{service}` = `/api/v1/{service}/...`。所以**新服务的 router 必须用 `prefix="/v1/{service}"`**，否则聚合后路径错乱。

### 18.4 共享资源与 `owns_*` 判定

`SharedResources`（`services_common.shared_resources`）是个通用注册表：`register(key, resource, closer=...)` 注册、`get_db()`/`get_redis()` 取、`close_all()` 倒序关闭。

每个服务 `setup` 的 owns 判定（**owns 逻辑在各服务 setup 里，不在 services.py**）：

```python
owns_db_manager = shared_resources is None or shared_resources.get_db() is None
_db_manager = shared_resources.get_db() if shared_resources else None
if _db_manager is None:
    _db_manager = DatabaseManager(...)   # standalone 或 shared 没注册时自建

owns_redis_manager = shared_resources is None or shared_resources.get_redis() is None
# ...同理

async def cleaner():
    if owns_redis_manager:        # 只关自己 own 的，不重复关共享
        await _redis_manager.close()
    if owns_db_manager:
        await _db_manager.close()
```

- **standalone**（`shared_resources=None`）：`owns_*=True`，自建自关。
- **all-in-one**（shared 已注册）：`owns_*=False`，复用共享，cleaner 不关（由 `SharedResources.close_all()` 统一关）。
- 个别服务可强制自建（如某服务需要独立 DB schema 隔离）——在其 setup 里忽略 shared_resources 即可，但要自己管清理。

### 18.5 config.py：多继承 + `get_<service>_settings()` 访问器

`all-in-one/src/all_in_one/config.py` 的 `Settings` **多继承所有服务的 Settings**：

```python
class Settings(AllInOneSettings, PingPongSettings, AccountSettings, ContentSettings, ...):
    APP_NAME: str = "all-in-one"
    MODEL: str = "all-in-one"                    # ← 覆盖 AppSettings 默认 "standalone"
    ALL_IN_ONE_SHARE_DB: bool = True
    ALL_IN_ONE_SHARE_REDIS: bool = True
```

每个服务一个访问器，统一三步覆盖：

```python
def get_account_settings(self):
    config_dict = vars(self).copy()
    config_dict.update({
        "MODEL": "all-in-one",                    # 强制 all-in-one（触发 local_api）
        "APP_NAME": self.APP_NAME + "-account",   # 各服务 APP_NAME 加后缀区分
        "REDIS_PREFIX": "acc",                    # 各服务 Redis key 前缀
    })
    return AccountSettings(**config_dict)
```

> 含 Celery 的服务（content-ops、data-collector）访问器还要**显式透传 Celery 字段**（`CELERY_BROKER_URL`/`CELERY_TASK_ROUTES` 等），因为 `vars(self)` 拿不到默认值会回退到 `services_common` 的 db4/db5。

### 18.6 clients 在两种模式下的切换

`clients/<依赖>/api_proxy.py` 读 `settings.MODEL`：

```python
if setting.MODEL == "all-in-one":
    self.proxy = LocalUserService()      # 进程内：get_injector().get(姊妹服务 Service)
else:
    self.proxy = RemoteUserService(base_url=setting.XXX_SERVICE_URL)  # httpx
```

- all-in-one：走 `local_api`，直连 injector 取姊妹服务的 application 对象，**零网络开销**。
- standalone：走 `remote_api`，httpx 调 `XXX_SERVICE_URL`。
- 这就是"同一份业务代码两种模式无差别"的开关。

### 18.7 把一个新服务接入 All-in-One（完整清单）

让脚手架生成的新服务也能跑进 `make all-in-one`，需手动 7 步：

1. **根 `pyproject.toml`**：`[tool.uv.workspace].members` 加 `services/<service>`，`[tool.uv.sources]` 加 `<service> = { workspace = true }`。（脚手架 `generate-service` 已自动做这步）
2. **`all-in-one/pyproject.toml`** 的 `dependencies` 加 `"<service>"`。
3. **`all-in-one/src/all_in_one/config.py`**：
   - `from <pkg>.foundation.config import Settings as <Pascal>Settings`
   - 把它加进 `Settings` 多继承基类列表
   - 写 `get_<service>_settings()` 访问器（设 MODEL/APP_NAME/REDIS_PREFIX，含 Celery 则透传 Celery 字段）
4. **`all-in-one/src/all_in_one/services.py`**：加一段 try/except 加载块（`from <pkg>.main import setup` → `get_<service>_settings()` → `await setup(app, ..., shared_resources=shared_resources)` → 标记 enabled）。非必需服务用 `logger.warning`，必需服务用 `raise RuntimeError`。
5. **`deploy/Dockerfile.all-in-one`**：加 `COPY services/<service> /workspace/services/<service>` 和 `RUN uv pip install --system -e ./services/<service> ...`。
6. **`deploy/scripts/migrate.sh`**：加一行 `run_migration "services/<service>" "<service>"`。
7. **本服务的 `app/api/v1/router.py`** 必须用 `prefix="/v1/<service>"`，`setup` 必须接受 `shared_resources` 参数并实现 owns_* 逻辑（脚手架模板已具备）。

### 18.8 All-in-One 的启动

```bash
# 开发（热重载，默认 8002，可覆盖）
make all-in-one
make all-in-one ALL_IN_ONE_PORT=9000      # 换端口
make all-in-one-watch                      # watchfiles 监听 services/ 与 all-in-one/src
```

- dev 的 PYTHONPATH 显式拼 `services/common/src : services/pingpong-service/src : all-in-one/src`，其余服务靠 uv workspace editable install。
- 生产容器（`deploy/Dockerfile.all-in-one`）：`uv pip install --system -e` 装全部 19 个服务 → `python -m uvicorn all_in_one.main:app --host 0.0.0.0 --port 8002 --workers 4 --loop uvloop`（容器内固定 8002，宿主映射 8002）。
- 健康检查：`curl http://localhost:8002/health`，返回 `{status, mode, services:[已加载服务列表]}`。注意 `/health` 永远返回 healthy，它列的是**已加载**的服务，不反映单服务健康度。

### 18.9 迁移

all-in-one 共享一个 DB，所有服务的表共存（靠 `service_prefix_` 表名前缀隔离）。迁移用 `deploy/scripts/migrate.sh`：从运行中的容器读 `DATABASE_URL`，对每个服务 `docker exec -w /workspace/services/<service> <container> alembic upgrade head`。迁移顺序与加载顺序不同（migrate 把 pingpong 放最后）。默认迁移完不重启容器（`RESTART_CONTAINER=false`）。

### 18.10 All-in-One 常见坑

| 现象 | 原因 / 解决 |
|---|---|
| 聚合后某服务路由 404 | 该服务 `router.py` 没用 `prefix="/v1/{service}"`，或 `services.py` 加载块写成 `logger.warning` 吞了异常——看启动日志 `Failed to load xxx` |
| 跨服务调用拿到错误服务 | 直接共享了 injector。跨服务**必须走 `clients/local_api.py`**，不要 `get_injector().get()` 跨服务取（全局 injector 是最后注册服务的） |
| `local_api` 取不到姊妹服务 | 姊妹服务加载失败（被 warning 跳过）或加载顺序在后。看 `/health` 的 services 列表是否含它 |
| Celery 服务在 all-in-one 用了 db4/db5 | 访问器没透传 `CELERY_BROKER_URL`，回退到 `services_common` 默认。在 `get_<service>_settings()` 显式透传 |
| 启动直接挂 | `data-collector-service` 加载失败（必需），看 `Failed to load required data-collector-service` 堆栈 |
| 表名冲突 | 某服务 ORM 表名忘加 `service_prefix_` 前缀，与别的服务撞表 |
| `/health` 显示 healthy 但某服务不可用 | `/health` 不反映单服务健康，只列已加载的。要看启动日志的 warning |

---

## 19. 日志、中间件、异常处理

### 中间件链（`main.py` 装配，后加先执行）

```
请求 → RequestIDMiddleware → ErrorHandlingMiddleware → LoggingMiddleware → CORS → 路由
```

- `RequestIDMiddleware`：注入 `request_id`，贯穿日志与响应。
- `ErrorHandlingMiddleware`：兜底未捕获异常。
- `LoggingMiddleware`：请求/响应日志。

### 日志

`foundation/logging.py` 封装 `services_common.logging.Logger`。用法：

```python
from pingpong_service.foundation.logging import get_logger
logger = get_logger(__name__)

logger.info("查询 ping", operation="pingpong.ping.get_by_id", ping_id=pid)
logger.error("创建失败", operation="pingpong.pong.create.fail", error=str(e))
```

约定：**每条日志带 `operation=...`**（语义化操作标识），结构化 kwarg 传上下文，不要 f-string 拼大段。

### 异常处理

- 业务异常：抛 `BaseDomainException` / `BaseApplicationException` 子类（绑 `BizCode`），`register_base_exception_handlers` 会转成带 biz_code 的 `DataResponse`（HTTP 400）。
- 校验错误：FastAPI 自动 422（dev 模式带 detail）。
- 未知异常：统一 500，**不泄露堆栈**。

---

## 20. 测试

### 20.1 现状

模板的 `tests/` 较薄，当前是集成风格：调 `get_injector()` 取实例（需要 app 已启动）。pytest 配置：`asyncio_mode = "auto"`，`testpaths = ["tests"]`。

```bash
make test-service SERVICE=<service>
make lint-service SERVICE=<service>   # ruff + mypy
```

### 20.2 推荐写法

- **单元测试**：在测试里自建一个局部 `Injector`（传入 mock 的 `DatabaseManager`/`RedisManager`/clients），断言 Command/Query 逻辑。
- **集成测试**：起真实 DB/Redis（`make compose-up`），跑完整用例。
- 异步测试用 `@pytest.mark.asyncio`。
- 用 `BizCodeTestQuery` 的模式验证 biz_code 链路：制造一个会抛异常的用例，断言响应 envelope 的 `biz_code`。

### 20.3 Lint / 类型

```bash
make lint-service SERVICE=<service>
# = ruff check . && mypy src/
```

ruff：`line-length=100`、`target-version=py312`。mypy：`strict=true`。**提交前必须过**。

---

## 21. 编码规范与提交前检查清单

### 规范要点

- **一个文件一个职责**：一个聚合/Entity/VO/Repository/ORM Model/Command/Query/Service/Endpoint/Schema 各占一文件。
- **命名**（生成器已强制）：服务目录 `<名>-service`（kebab），包 `<名>_service`（snake），Repository 接口 `<聚合>Repository`，实现 `SQL<聚合>Repository`，ORM 类 `<Prefix><表>Model`，表 `<prefix>_<表>`。
- **import 用完整路径**，不靠 `__init__.py` 默认导出。
- **无裸 dict 跨边界**，返回值用 dataclass / pydantic。
- **DB 操作必 async**，禁用同步 DB。
- **新增依赖必登记**对应 `modules.py`。

### 提交前清单（逐项 ✅）

- [ ] 目录结构合规（无多余顶层目录，符合四层 + foundation + clients + pkg）
- [ ] 依赖方向正确（api→application→domain←infrastructure；domain 无框架依赖）
- [ ] 四种载体不串层（ORM Model 不出 infrastructure，DTO 不进 domain，无裸 dict）
- [ ] ORM 表名/类名带前缀
- [ ] Repository 返回 Entity，有 `_to_entity`/`_to_model`，无 ORM 跨边界
- [ ] 所有异常绑定 BizCode；`BizCode` 成员有中文注释；无手写裸 biz_code 数字
- [ ] clients 五件套齐全；`app/` 内无 httpx；无裸 dict 返回
- [ ] 新依赖在对应 `modules.py` 注册
- [ ] 迁移文件已检查；`make migrate-service` 通过
- [ ] `make lint-service` 过；`make test-service` 过
- [ ] 模板里的 demo/占位代码已替换为真实业务（或已删除）

> 这份清单等价于 `develop/ai-coding-service-app.md §12`，提交前请对照。

---

## 22. 从开发到部署

> 实际部署资产在 `deploy/` 下。以 `deploy/` 为准。

### 22.1 本地依赖

```bash
make compose-up        # 读 deploy/local/docker-compose.yml，起 PostgreSQL + Redis
make compose-down
```

### 22.2 单服务镜像

每个服务有自己的 `Dockerfile`（注意：**从仓库根构建**，因为 `COPY services/<svc>/...`）：

```bash
make docker-build-service SERVICE=<service>
# 或在服务目录里 make docker-build
```

Dockerfile 模式：

```dockerfile
FROM python:3.12-slim AS base
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN pip install uv
COPY services/<svc>/pyproject.toml /app/
RUN uv pip install --system -e .
COPY services/<svc>/src /app/src
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1
EXPOSE <port>
CMD ["uvicorn", "<pkg>.main:app", "--host", "0.0.0.0", "--port", "<port>"]
```

### 22.3 All-in-One 生产部署

生产用 `make all-in-one-prod`（gunicorn + 4 uvicorn workers，端口 8000）。部署脚本与配置在 `deploy/`：

- `deploy/Dockerfile.all-in-one`：聚合镜像
- `deploy/scripts/deploy-all-in-one.sh`：部署脚本
- `deploy/config/all-in-one.env(.example)`：生产环境变量
- `deploy/scripts/migrate.sh`：启动前跑迁移

典型上线流程：

```bash
# 1. 构建聚合镜像（在 CI 或本机仓库根）
# 2. 配好 deploy/config/all-in-one.env
# 3. 部署（脚本内部：拉镜像 → migrate.sh → 启动 → 健康检查）
deploy/scripts/deploy-all-in-one.sh
```

### 22.4 不要忘了

- 部署后**跑迁移**（`migrate.sh`）。
- 健康检查端点 `/health`。
- 生产关 `DEBUG`（关 Swagger `/docs`）。
- 日志落盘配置（`LOG_FILE=true`、`LOG_DIR`）。
- 回滚：`deploy/README.md` 有回滚说明。

---

## 23. 常见坑与排错

| 现象 | 原因 / 解决 |
|---|---|
| `Injector not initialized` | `get_injector()` 在 app 启动前被调。检查测试是否需要先建局部 injector，或 main 的 lifespan 是否跑了。 |
| injector 解析某依赖报错 | 该依赖没在对应 `modules.py` 注册，或构造参数无法注入。补 `binder.bind(...)`。 |
| all-in-one 模式下表名冲突 | 忘了给 ORM 表名加 `service_prefix_` 前缀。 |
| Alembic 迁移了别的服务的表 | `SERVICE_TABLE_PREFIXES` 没配对，或 `version_table` 没用前缀。 |
| 客户端在 standalone 模式打不通 | `OTHER_SERVICE_URL` 没配；或 `settings.MODEL` 没设成 `standalone`，走了 local 分支找不到姊妹服务。 |
| 响应没有 biz_code | 异常没绑 `BizCode`，或没继承 `BaseDomainException`/`BaseApplicationException`。 |
| biz_code 数字手写出错 | 改用 `make_biz_code(SERVICE_CODE, BizCategory.XXX, 序号)`。 |
| mypy 报 strict 错误 | 补类型注解；ORM Model 字段、Repository 返回类型都要标注。 |
| 端点里有业务逻辑 | 抽到 application 层。api 只做校验/鉴权/调用/组装。 |
| `infrastructure/docker-compose.yml` 找不到 | 这是文档漂移，实际用 `deploy/local/docker-compose.yml`。 |
| 端口冲突（多个服务在 `service.metadata` 里用了同一端口） | 本地同时跑会冲突，单跑无碍；新服务选端口前先查所有 `service.metadata` 的 `port` 字段避免重复。 |
| 路由 path / tags 用了 `_` 或中文 | HTTP 路由一律 kebab（`/api-keys`、`tags=["api-keys"]`），文件名才用 snake。见 §11.4。tags 用全小写英文，不要 `API Keys`/`用量操作`。 |

---

## 24. 完整示例：实现一个 Article 资源

把前面串起来，实现一个 `article` 资源（创建文章 / 查询文章），假设服务 `my-app-service`（prefix `mapp`，code 20）。

### 步骤 1：domain

```python
# app/domain/entities/article.py
class Article(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    article_id: str
    title: ArticleTitle          # VO
    body: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

# app/domain/value_objects/article_title.py
class ArticleTitle:
    def __init__(self, raw: str):
        if not raw or len(raw) > 200: raise ValueError("title 长度需在 1-200")
        self._value = raw
    def __str__(self): return self._value

# app/domain/repositories/article_repository.py
class ArticleRepository(ABC):
    @abstractmethod
    async def get_by_id(self, article_id: str) -> Article | None: ...
    @abstractmethod
    async def create(self, article: Article) -> Article: ...

# app/domain/common/exceptions.py
class ArticleNotFoundException(BaseDomainException):
    def __init__(self, article_id: str):
        super().__init__(f"article not found: {article_id}",
                         code="ARTICLE_NOT_FOUND", biz_code=BizCode.ARTICLE_NOT_FOUND)
```

### 步骤 2：biz_code

```python
# foundation/biz_code.py
SERVICE_CODE = 20
class BizCode(IntEnum):
    SUCCESS = make_biz_code(SERVICE_CODE, BizCategory.SUCCESS, 0)
    ARTICLE_NOT_FOUND = make_biz_code(SERVICE_CODE, BizCategory.NOT_FOUND, 1)  # 文章不存在
    ARTICLE_ALREADY_EXISTS = make_biz_code(SERVICE_CODE, BizCategory.CONFLICT, 2)  # 文章已存在
```

### 步骤 3：infrastructure

```python
# app/infrastructure/persistence/models/article_model.py
class MAPPArticleModel(BaseModel):
    __tablename__ = "mapp_article"
    article_id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False)

# app/infrastructure/persistence/repositories/sql_article_repository.py
class SQLArticleRepository(ArticleRepository):
    @inject
    def __init__(self, dm: DatabaseManager, log_manager: LogManager):
        self._dm = dm
        self._logger = log_manager.get_logger(__name__)

    async def get_by_id(self, article_id: str) -> Article | None:
        async with self._dm.session() as s:
            m = (await s.execute(select(MAPPArticleModel).where(...))).scalar_one_or_none()
            return self._to_entity(m) if m else None

    async def create(self, article: Article) -> Article:
        async with self._dm.session() as s:
            m = self._to_model(article)
            s.add(m); await s.commit(); await s.refresh(m)
            return self._to_entity(m)

    def _to_entity(self, m): return Article(article_id=m.article_id, title=m.title, body=m.body, created_at=m.created_at)
    def _to_model(self, e): return MAPPArticleModel(article_id=e.article_id, title=str(e.title), body=e.body, created_at=e.created_at)

# app/infrastructure/modules.py — 加绑定
binder.bind(ArticleRepository, to=SQLArticleRepository, scope=None)
```

加迁移：`make migration-create SERVICE=my-app-service NAME=create_article`，检查后 `make migrate-service`。

### 步骤 4：application

```python
# app/application/commands/create_article.py
@dataclass
class CreateArticleResult:
    article: Article

class CreateArticleCommand:
    @inject
    def __init__(self, repo: ArticleRepository):
        self.repo = repo
    async def execute(self, title: str, body: str) -> CreateArticleResult:
        article = Article(article_id=generate_id(), title=ArticleTitle(title), body=body)
        saved = await self.repo.create(article)
        return CreateArticleResult(article=saved)

# app/application/queries/get_article.py
@dataclass
class GetArticleResult:
    article: Article | None
class GetArticleQuery:
    @inject
    def __init__(self, repo: ArticleRepository):
        self.repo = repo
    async def execute(self, article_id: str) -> GetArticleResult:
        return GetArticleResult(article=await self.repo.get_by_id(article_id))

# app/application/modules.py — 加绑定
binder.bind(CreateArticleCommand, to=CreateArticleCommand, scope=None)
binder.bind(GetArticleQuery, to=GetArticleQuery, scope=None)
```

### 步骤 5：api

```python
# app/api/v1/schemas/article.py
class CreateArticleRequest(BaseModel):
    title: str; body: str
class ArticleResponse(BaseModel):
    article_id: str; title: str; body: str; created_at: datetime
class ArticleDataResponse(DataResponse[ArticleResponse]): pass

# app/api/v1/endpoints/articles.py
router = APIRouter(prefix="/articles", tags=["articles"])

def get_create_cmd() -> CreateArticleCommand: return get_injector().get(CreateArticleCommand)
def get_get_query() -> GetArticleQuery: return get_injector().get(GetArticleQuery)

@router.post("", response_model=ArticleDataResponse)
async def create_article(req: CreateArticleRequest, cmd=Depends(get_create_cmd)):
    r = await cmd.execute(req.title, req.body)
    return success(data=ArticleResponse(article_id=r.article.article_id, title=str(r.article.title),
                                         body=r.article.body, created_at=r.article.created_at),
                   message="文章创建成功")

@router.get("/{article_id}", response_model=ArticleDataResponse)
async def get_article(article_id: str, q=Depends(get_get_query)):
    r = await q.execute(article_id)
    if r.article is None:
        raise ArticleNotFoundException(article_id)
    return success(data=ArticleResponse(...))

# app/api/v1/router.py
api_router = APIRouter(prefix="/v1/my-app")
api_router.include_router(articles_router)
```

### 步骤 6：验证

```bash
make dev SERVICE=my-app-service
curl -X POST http://localhost:8005/api/v1/my-app/articles -H 'Content-Type: application/json' \
     -d '{"title":"hello","body":"world"}'
curl http://localhost:8005/api/v1/my-app/articles/<id>
# 查一个不存在的 id，应当看到 biz_code 对应 ARTICLE_NOT_FOUND
make lint-service SERVICE=my-app-service
make test-service SERVICE=my-app-service
```

---

## 25. 附录：命令速查表

```bash
# ── 环境 ──
make install                            # 安装所有服务
make compose-up                         # 起本地 PostgreSQL + Redis
make compose-down

# ── 创建服务 ──
make generate-service SERVICE=xxx SHORT_PREFIX=yy SERVICE_CODE=20 PORT=8005
make install-service SERVICE=xxx-service

# ── 单服务开发 ──
make dev SERVICE=xxx-service            # uvicorn --reload
make dev-https SERVICE=xxx-service
make lint-service SERVICE=xxx-service   # ruff + mypy
make test-service SERVICE=xxx-service
make migrate-service SERVICE=xxx-service
make migration-create SERVICE=xxx-service NAME=add_xxx
make docker-build-service SERVICE=xxx-service
make health                             # curl 各服务 /health

# ── 批量 ──
make install / lint / test / migrate / docker-build / clean

# ── All-in-One ──
make all-in-one                         # 开发，端口 8002
make all-in-one-prod                    # 生产，gunicorn，端口 8000
make all-in-one-install

# ── workspace 管理 ──
make add-service SERVICE=xxx            # uv add --editable ./services/xxx
make remove-service SERVICE=xxx         # uv remove

# ── 部署（deploy/ 下）──
# 实际脚本：deploy/scripts/deploy-all-in-one.sh / deploy.sh / migrate.sh
```

---

> 下一步阅读：
> - `develop/worker-development-guide.md` — Worker 开发指南（姊妹篇）
> - `develop/ai-coding-service-app.md` — 完整约束规范（红线全集）
> - `services/pingpong-service/` — 参考实现，对照本文读源码

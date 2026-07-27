# AI 编程约束范式 - 微服务（services/）开发规范

> **重要提醒**：在开发 `services/` 下的任何微服务时，你必须严格逐条遵循本规范。无论上下文有多长，都不允许偏离。本规范的目标是**消除每次开发的差异性**——同一个需求，不同时间、不同人、不同 AI 来写，产出的结构必须一致。
>
> **遇到本规范未覆盖的情况**：不要自由发挥。先在 `services/` 现有服务中找一个最接近的已实现案例，对齐它的写法；仍无法判断时，停下来询问，不要擅自创造新模式。

---

## 0. 黄金法则（违反任意一条即为不合格）

1. **一个文件只放一个主类/一个职责**：禁止把同层多个类别（如多个 Repository、多个 Service）塞进一个文件。
2. **跨边界只传"定义好的类型"，禁止裸 `dict`**：层与层之间、`clients/` 的返回值，一律使用 Pydantic 模型 / dataclass / 领域实体，禁止 `-> dict` / `return {...}` 作为对外契约。
3. **依赖方向单向向内**：`api → application → domain ← infrastructure`，`clients` 被 `application` 依赖。严禁反向 import。
4. **抽象与实现分离**：`domain` 定义接口（ABC），`infrastructure` 写实现；`clients` 定义 `interface.py`，由 `api_proxy/remote_api/local_api` 实现。本服务存储走 `infrastructure`，外部服务走 `clients`，二者不得互相 import、不得串门（见 §2.1）。
5. **每个新增依赖必须在对应 `modules.py` 注册**，否则视为未完成。`modules.py` 的 import 一律写在 `configure()` 方法体内（见 §6.1.1）。
6. **入口即转载体**：payload/DTO/响应 JSON 一跨过层边界立即转成该层载体，绝不把上一层类型泄漏到下一层。HTTP body→DTO（api）、DTO→Entity（application 入口）、HTTP 响应→Client Schema（clients）、Entity↔ORM（infrastructure `_to_*`）。

## 0.1 占位符与命名推导（消除"怎么从服务名推出各种名字"的歧义）

本规范大量使用 `{pkg}`、`{SERVICE_PREFIX_UPPER}`、`{聚合}` 等占位符。它们**必须**从 `service.metadata` 按下表严格推导，不得自由命名。AI 产出前先填这张表，再据此生成所有文件名/类名/import 路径。

设 `service.metadata` 为：

```json
{ "service_name": "content_quality", "service_prefix": "cqal", "port": "8019", "service_code": 6 }
```

| 占位符 | 推导规则 | 本例取值 | 用在哪里 |
|---|---|---|---|
| `{kebab}` | `service_name` 的 `_` → `-` | `content-quality` | 服务目录名 `{kebab}-service` |
| `{snake}` | `service_name`（已是 snake） | `content_quality` | 包目录名 `{snake}_service`、DB 名 `{kebab}-db` |
| `{pkg}` | = `{snake}_service` | `content_quality_service` | **所有 import 根**，如 `from {pkg}.app.domain...` |
| `{pascal}` | `service_name` 各段首字母大写拼接 | `ContentQuality` | 服务级类名 `class {Pascal}Service`、FastAPI title |
| `{prefix}` | `service_prefix`（全小写原样） | `cqal` | **表名前缀** `cqal_xxx`、Redis 前缀、alembic version_table |
| `{SERVICE_PREFIX_UPPER}` | `{prefix}` 全大写 | `CQAL` | **ORM 类名前缀** `class {SERVICE_PREFIX_UPPER}{表}Model` → `CQALUserModel`；自定义配置项前缀 `CQAL_XXX` |
| `{service_code}` | `service.metadata` 的 `service_code` | `6` | 写入 `foundation/biz_code.py` 的 `SERVICE_CODE` |

**硬约束**：
- ORM 类名前缀一律用 `{SERVICE_PREFIX_UPPER}` —— **`service_prefix` 整体转全大写**（不是首字母大写、不是只大写一段）。`acc`→`ACC`、`pipo`→`PIPO`、`cqal`→`CQAL`、`dcol`→`DCOL`。
- 表名前缀一律用 `{prefix}`（全小写原样）。**类名前缀与表名前缀来自同一个 `service_prefix`，仅大小写不同**：表 `cqal_user` ↔ 类 `CQALUserModel`、表 `pipo_ping` ↔ 类 `PIPOPingModel`。
- import 根一律用 `{pkg}`（如 `from content_quality_service.app.domain...`），**不要**用 `{snake}` 或 `{kebab}`。
- ❌ **不要**把 ORM 类名前缀写成首字母大写（`CqalUserModel`）或无前缀（`UserModel`）。目的见 §5.4：all-in-one 合并运行时多个服务共享同一 SQLAlchemy `DeclarativeBase`，类名不带服务前缀或前缀风格不统一都会冲突 / 难以辨识归属服务。

> ⚠️ **优先复刻 pingpong-service 模板**：所有命名推导已硬编码在 `generate-service` 脚本的替换表里。脚手架生成后，包名/前缀/import 根已经是正确的——**AI 不得重命名任何目录或顶层包**，只需在 `app/` 内按业务新增文件。

## 0.2 脚手架后的改写流程（收到新服务需求时的操作序列）

`generate-service` 后得到的服务继承了 pingpong 的 demo 代码（端点 `pp_demo.py`→重命名为 `{域}_demo.py`、command `create_pong.py`、entity `Ping/Pong` 等）。这些是**占位示例，不是业务代码**。AI 不得在 demo 文件上直接改业务，必须按下列流程改写：

**第一步：先确定本服务的聚合与用例**（动代码前先想清楚）
1. 列出本服务的聚合根（如 `User`、`Order`）——每个聚合对应一个 domain entity + repository + ORM Model + SQL Repository。
2. 列出每个用例的归类（按 §5.2 决策树）：只读→Query；单聚合写→Command；跨聚合/多步→application service；纯领域规则→domain service。
3. 列出外部依赖：哪些是本服务存储（→infrastructure），哪些是调别的服务/第三方（→clients）。

**第二步：清理 demo 代码**（避免 demo 逻辑污染业务）
- 删除/清空 demo 的 application 代码（`create_pong.py`、`get_ping.py`、`pp_service.py`、`biz_code_test.py`）、demo 的 api 端点（`*_demo.py`）。
- domain 的 `Ping/Pong` 实体、`PingRepository/PongRepository` 接口、对应 ORM Model 与 SQL Repository——若本服务确实没有 pingpong 概念，删除；保留的话务必改名归到真实聚合。
- 删除后 `modules.py` 里对应的 `binder.bind(...)` 也要同步删除（否则引用已删类致 import 报错）。
- `foundation/biz_code.py` 的 demo BizCode 成员（`PAP_NOT_FOUND` 等）删除或改名，按 §13.4.1 重新规划本服务真实业务码。

**第三步：按 §0.1 推导的名字，按附录 A 的结构逐层新建业务文件**
- 顺序：domain（entities→value_objects→repositories→common/exceptions）→ biz_code → infrastructure（models→repositories→modules）→ application（commands/queries/services→modules）→ clients（如需）→ api（schemas→endpoints→router）。
- 每新增一个"可注入的类"立即在对应 `modules.py` 加 `binder.bind`（§6.1.1）。

**第四步：alembic 迁移**
- 改完 ORM Model 后 `make migration-create` 生成迁移，**人工检查** `upgrade()`/`downgrade()`，`make migrate-service` 应用。

**第五步：对照第 §12 清单逐条核对**再交付。

> 关键判据：交付后仓库里**不应遗留任何 `pong`/`ping`/`PAP`/`pp_demo`/`biz_code_test` 等模板词**（除非本服务真有同名业务）。grep不到 demo 残留 = 改写干净。

---

## 1. 项目结构规范

每个微服务必须遵循以下目录结构（以 `{服务名}-service` 为根，包名为 `{服务名_下划线}_service`）：

```
{服务名}-service/
├── src/
│   └── {服务名_underscore}_service/
│       ├── app/
│       │   ├── api/
│       │   │   └── v1/
│       │   │       ├── common/             # 公共依赖（鉴权、Token 解析等 FastAPI Depends）
│       │   │       ├── endpoints/          # API 端点（一资源一文件）
│       │   │       ├── schemas/            # 请求/响应 DTO（Pydantic）
│       │   │       └── router.py           # 路由聚合
│       │   ├── application/                # 应用层 (CQRS)
│       │   │   ├── commands/               # 命令处理器（写操作，一用例一文件）
│       │   │   ├── queries/                # 查询处理器（读操作，一用例一文件）
│       │   │   ├── services/               # 应用服务（跨用例/事务编排）
│       │   │   ├── common/                 # 应用层公共（应用异常等）
│       │   │   └── modules.py              # 应用层 DI 注册
│       │   ├── domain/                     # 领域层（最纯净，无框架依赖）
│       │   │   ├── entities/               # 领域实体 / 聚合根
│       │   │   ├── value_objects/          # 值对象（不可变）
│       │   │   ├── repositories/           # 仓储接口（ABC）
│       │   │   ├── caches/                 # 缓存接口（ABC，可选）
│       │   │   ├── common/                 # 领域异常等
│       │   │   └── modules.py              # 领域层 DI 注册
│       │   └── infrastructure/             # 基础设施层（实现 domain 接口）
│       │       ├── persistence/
│       │       │   ├── models/             # SQLAlchemy ORM 模型（一表一文件）
│       │       │   └── repositories/       # 仓储实现（一聚合一文件）
│       │       ├── caches/                 # 缓存实现
│       │       ├── security/               # 安全实现（密码哈希等，可选）
│       │       └── modules.py              # 基础设施层 DI 注册
│       ├── clients/                        # 外部请求/服务交互（一外部依赖一目录）
│       │   └── modules.py                  # clients DI 注册
│       ├── foundation/                     # 基础组件
│       │   ├── config.py                   # 配置
│       │   ├── container.py                # 依赖注入容器
│       │   ├── logging.py                  # 日志
│       │   ├── biz_code.py                 # 服务业务码定义（SERVICE_CODE + BizCode 枚举）
│       │   └── exception_handlers.py       # 全局异常处理（可选）
│       └── pkg/                            # 与业务无关的纯工具（utils/sdk）
├── alembic/                               # 数据库迁移
├── tests/
├── pyproject.toml
├── service.metadata                       # 服务元数据（含 service_prefix）
├── Dockerfile
└── Makefile
```

> ⚠️ **目录即契约**：不允许新增上述清单之外的顶层目录；不允许把某层的文件放到另一层目录。

---

## 2. 分层依赖方向矩阵（核心，必须严格执行）

下表规定每一层**允许 import 的目标**。"✅允许 / ❌禁止"是硬约束。

| 来源 \ 目标 | api | application | domain | infrastructure | clients | foundation | services_common |
|---|---|---|---|---|---|---|---|
| **api/endpoints** | ✅同层 | ✅(只调用 command/query/service) | ✅(仅类型注解/实体只读) | ❌ | ❌ | ✅ | ✅ |
| **application** | ❌ | ✅同层 | ✅ | ❌(只依赖 domain 抽象接口) | ✅ | ✅ | ✅ |
| **domain** | ❌ | ❌ | ✅同层 | ❌ | ❌ | ⚠️仅纯类型/异常基类 | ⚠️仅纯类型 |
| **infrastructure** | ❌ | ❌ | ✅(实现其接口) | ✅同层 | ❌ | ✅ | ✅ |
| **clients** | ❌ | ❌ | ⚠️仅当需要返回领域类型时 | ❌ | ✅同层 | ✅(config) | ✅ |
| **foundation** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |

**关键红线**：
- **api 不得 import infrastructure**：端点拿不到任何 `SQLxxxRepository`、ORM Model、Redis 实现。
- **application 不得 import infrastructure 的具体实现**：只能依赖 `domain` 里的抽象接口，由 DI 注入实现。
- **domain 不得依赖任何外部框架**：不出现 `sqlalchemy`、`redis`、`httpx`、`fastapi`、`injector` 的业务调用（`injector` 仅在外层注入时使用，domain 类本身不写 `@inject`）。
- **domain 内部禁止 import application / infrastructure / api / clients**。

数据流（唯一合法方向）：

```
HTTP 请求 → api/endpoints → application(command/query/service) → domain(实体+仓储接口) ← infrastructure(仓储实现/ORM)
                                        ↓
                                    clients(外部服务)
```

### 2.1 clients 与 infrastructure 的边界（高频踩坑，单独强调）

这是 AI 最常跑偏的红线：**把外部服务/外部接口调用写进 `infrastructure/`**。两类"外部依赖"职责严格分离，不得串门：

| 维度 | `infrastructure/`（持久化适配器） | `clients/`（外部服务适配器） |
|---|---|---|
| 适配对象 | **本服务自己的** DB 表、Redis 缓存（通过 domain 的 Repository/Cache 接口实现） | **别的服务/第三方**（HTTP API、SDK：account-service、github、aliyun_sms…） |
| 实现的接口 | `domain/repositories/`、`domain/caches/` 的 ABC | `clients/{依赖}/interface.py` 的 ABC |
| 用到的技术 | SQLAlchemy ORM、asyncpg、redis（本服务存储） | httpx、第三方 SDK（网络调用） |
| 谁依赖它 | application 注入 `domain` 接口 → DI 解析到 infrastructure 实现 | application 注入 `clients` 接口 → DI 解析到 clients 的 APIProxy/Remote |
| 禁止 | ❌ 出现 `httpx`、❌ 调别的服务的 HTTP、❌ 调第三方 SDK | ❌ 操作本服务 DB/ORM、❌ import infrastructure |

**判断口诀**：
- 落**本服务自己库**的 → `infrastructure/persistence/`。
- 走**网络调别的服务/第三方**的 → `clients/`。
- 两者**都不属于 domain**，domain 只持有抽象接口（Repository 在 `domain/repositories/`，外部服务接口在 `clients/interface.py`——注意这俩接口的归属不同，因为外部服务接口本身是防腐层概念，放 clients 更内聚）。

```python
# ❌ 错误：把调 account-service 写进 infrastructure
# app/infrastructure/persistence/repositories/sql_user_repository.py
class SQLUserRepository(UserRepository):
    async def get_user(self, uid):
        async with httpx.AsyncClient() as c:          # ← httpx 出现在 infrastructure，红线
            resp = await c.get(f"http://account/api/v1/users/{uid}")
            ...

# ✅ 正确：调外部服务走 clients，infrastructure 只碰自己的库
# clients/account_service/remote_api.py 里用 httpx
# app/infrastructure/.../sql_user_repository.py 只操作 ACCUserModel（本服务表）
```

> domain 的 Repository 接口只描述**本服务聚合**的持久化；若一个用例需要"查本服务订单 + 查外部用户信息"，application 层同时注入 `OrderRepository`（domain→infrastructure）和 `AccountService`（clients interface→APIProxy），二者在 application 内协作，**绝不**让 infrastructure 去调 clients，也**绝不**让 clients 去碰 ORM。

---

## 3. 三种数据结构的边界与转换（解决"直接拼 dict 返回"问题）

系统中**只允许存在四类数据载体**，各有明确归属层与转换边界，**禁止跨边界直接传裸 `dict`**：

| 载体 | 定义位置 | 用途 | 谁能见到 |
|---|---|---|---|
| **DTO (Schema)** | `app/api/v1/schemas/` | HTTP 请求体/响应体 | api 层、application 层入参/出参 |
| **Entity / Value Object** | `app/domain/entities`、`value_objects/` | 业务核心对象 | domain、application、infrastructure |
| **ORM Model** | `app/infrastructure/persistence/models/` | 数据库行映射 | 仅 infrastructure 内部 |
| **Client Schema** | `clients/{服务}/schemas.py` | 外部服务的请求/响应契约 | 仅 clients 内部 + 作为 clients 方法返回值 |

### 3.1 转换规则（硬约束）

```
[HTTP 入] DTO ──(command/query 内转换)──> Entity/VO
[持久化]  Entity ──(repository._to_model)──> ORM Model ──写库
[读取]    ORM Model ──(repository._to_entity)──> Entity ──返回 application
[HTTP 出] Entity ──(command/query 或 endpoint 组装)──> DTO ──> success(data=DTO)
[外部调用] Client Schema ──(clients 方法返回)──> application 再转 Entity/DTO
```

- **ORM Model 绝对不能越过 infrastructure 边界**：repository 的返回值必须是领域 Entity，禁止把 `XxxModel` 直接返回给 application。
- **DTO 绝对不能进入 domain/infrastructure**：domain 不认识 api 的 schema。
- **每个 Repository 实现必须提供 `_to_entity()` 和 `_to_model()` 私有方法**完成转换（见 §6.3）。
- 端点返回必须是 `DataResponse[具体DTO]`，**禁止** `response_model` 缺省或返回裸 `dict`。

### 3.2 反面案例（禁止）

```python
# ❌ 禁止：clients 直接拼 dict 返回
async def get_user(self, uid: str) -> dict:
    resp = await client.get(...)
    return {"id": resp.json()["id"], "name": resp.json()["name"]}

# ❌ 禁止：repository 返回 ORM Model
async def get_by_id(self, id: str) -> ACCUserModel:
    return await session.get(ACCUserModel, id)

# ❌ 禁止：endpoint 返回裸 dict
@router.get("/users/{uid}")
async def get_user(uid: str):
    return {"id": uid, "name": "x"}
```

### 3.3 正确案例

```python
# ✅ clients 返回 Client Schema（Pydantic）
async def get_user(self, uid: str) -> UserInfo:
    resp = await client.get(f"/api/v1/users/{uid}")
    data = resp.json().get("data", {})
    return UserInfo(**data)

# ✅ repository 返回领域实体
async def get_by_id(self, id: str) -> Optional[User]:
    model = await session.get(ACCUserModel, id)
    return self._to_entity(model) if model else None

# ✅ endpoint 返回 DataResponse[DTO]
@router.get("/users/{uid}", response_model=DataResponse[UserResponse])
async def get_user(uid: str, q: GetUserQuery = Depends(get_user_query)) -> DataResponse[UserResponse]:
    user = await q.execute(uid)            # 返回 Entity
    return success(data=UserResponse.model_validate(user))
```

---

## 4. SOLID 文件拆分规则（解决"同层多类别塞一个文件"问题）

### 4.1 一文件一职责（强制）

| 目录 | 拆分粒度 | 命名 | 示例 |
|---|---|---|---|
| `domain/entities/` | 一个聚合根/实体一个文件 | `{实体}.py` | `user.py` → `class User` |
| `domain/value_objects/` | 一个值对象一个文件 | `{vo}.py` | `email.py` → `class Email` |
| `domain/repositories/` | 一个聚合一个接口文件 | `{聚合}_repository.py` | `user_repository.py` → `class UserRepository(ABC)` |
| `domain/caches/` | 一个缓存域一个接口文件 | `{域}_cache.py` | `user_cache.py` |
| `infrastructure/persistence/models/` | 一张表一个文件 | `{表}_model.py` | `user_model.py` → `class ACCUserModel` |
| `infrastructure/persistence/repositories/` | 一个聚合一个实现文件 | `sql_{聚合}_repository.py` | `sql_user_repository.py` |
| `application/commands/` | 一个写用例一个文件（单聚合写） | `{动词}_{名词}.py` | `create_user.py` |
| `application/queries/` | 一个读用例一个文件（只读） | `get_{名词}.py` / `list_{名词}.py` | `get_user.py` |
| `application/services/` | 一个跨聚合/可复用流程一个文件 | `{流程}_service.py` | `order_placement_service.py` |
| `api/v1/endpoints/` | 一个资源一个文件 | `{资源}.py` | `users.py` |
| `api/v1/schemas/` | 一个资源一个文件 | `{资源}.py` | `user.py`（含 Request/Response 多个类） |
| `clients/{服务}/` | 一个外部依赖一个目录 | 见 §7 | `account_service/` |

### 4.2 SOLID 落地要点

- **S（单一职责）**：一个 Repository 只服务一个聚合根。`UserRepository` 不得混入订单查询。出现"又查用户又查订单"时，拆成两个 Repository。
- **O（开闭）**：扩展通过"新增文件 + DI 注册"实现，不修改已有实现类的内部分支。`clients` 的 local/remote 切换、broker 的工厂注册表都是范例。
- **L（里氏替换）**：`infrastructure` 实现必须完全满足 `domain` 接口签名；`local_api`/`remote_api` 必须完全满足 `interface.py`，返回类型一致。
- **I（接口隔离）**：接口按聚合/能力细分，禁止"大而全"的 `BaseRepository` 把所有方法塞进去让子类被迫实现空方法。
- **D（依赖倒置）**：上层依赖抽象（`domain` 接口 / `clients` interface），具体实现由 DI 注入。

### 4.3 何时允许一个文件多个类

仅以下情况允许：
- 同一资源的多个 DTO（如 `UserRequest`、`UserResponse`、`UserListResponse` 放在 `schemas/user.py`）。
- 紧密耦合、不可独立存在的实体与其值对象（如 `Ping` 与 `Pong` 在示例中共存，但生产代码优先拆分）。
- 同一文件内的私有辅助函数/`dataclass` 结果对象（如 command 的 `XxxCommandResult`）。

> 判断标准：**两个类是否会被独立 import、独立测试、独立演化**。会 → 拆分；不会 → 可共存。

---

## 5. 各层职责边界详解

### 5.1 API 层（`app/api/v1/`）

**只做四件事**：参数校验（DTO）、鉴权（common/Depends）、调用 application、组装 `DataResponse` 返回。

- ❌ 不写业务逻辑、不做循环计算业务规则、不直接访问数据库/Redis/外部 HTTP。
- ❌ 不 import `infrastructure`、不 import ORM Model。
- ✅ 通过 `Depends(get_xxx_query/command)` 从容器获取 application 对象。
- ✅ 路由前缀 `/api/v1/{服务名}`；**HTTP path / tags / name / operation_id 一律用 `-` 连接，禁止 `_`**（详见 §5.1.1）。
- ✅ 端点函数必须标注返回类型 `-> DataResponse[XxxDTO]`。

```python
# app/api/v1/endpoints/users.py  —— 文件名用 snake（api_keys.py），路由 path 用 kebab（/api-keys）
from fastapi import APIRouter, Depends, HTTPException, status
from services_common import success, DataResponse

from {pkg}.foundation.container import get_injector
from {pkg}.app.application.queries.get_user import GetUserQuery
from {pkg}.app.api.v1.schemas.user import UserResponse

# prefix/tags 用 kebab-case，与文件名 snake_case 区分开
router = APIRouter(prefix="/users", tags=["users"])


def get_user_query() -> GetUserQuery:
    return get_injector().get(GetUserQuery)


@router.get("/{user_id}", response_model=DataResponse[UserResponse], name="get_user")
async def get_user(
    user_id: str,
    query: GetUserQuery = Depends(get_user_query),
) -> DataResponse[UserResponse]:
    try:
        user = await query.execute(user_id)
        return success(data=UserResponse.model_validate(user))
    except Exception as e:
        logger.error("获取用户失败", operation="user.get.error", user_id=user_id, error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="获取用户失败")
```

### 5.1.1 路由命名规范（kebab-case，禁 `_`，AI 高频跑偏处）

HTTP 路由相关的**所有面向 URL / OpenAPI 的标识**统一用 **kebab-case（`-` 连接）**，禁止 `_`。**Python 文件名 / 类名 / 函数名 / 变量名**仍按 Python 惯例用 snake_case / PascalCase——二者不要混淆。

| 命名对象 | 用什么 | 示例 ✅ | 反例 ❌ |
|---|---|---|---|
| **HTTP path**（`@router.get(path)`、`APIRouter(prefix=)`） | kebab-case | `/api-keys/{key_id}`、`/user-profile` | `/api_keys/{key_id}`、`/user_profile` |
| **路径参数名** | snake_case（Python 变量，非 URL 段） | `/{user_id}`（参数 `user_id`） | `/{user-id}`（非法 Python） |
| **`tags`**（OpenAPI 分组） | kebab-case 英文，全小写 | `tags=["api-keys"]` | `tags=["API Keys"]`、`tags=["api_keys"]`、`tags=["用量操作"]` |
| **`name`**（路由名，用于 `url_for`） | snake_case（Python 标识符） | `name="get_user"` | `name="get-user"`（非法标识符） |
| **`operation_id`**（如设） | snake_case | `operation_id="get_user"` | `operation_id="get-user"` |
| **聚合 router prefix** | `/v1/{kebab服务名}` | `/v1/content-quality` | `/v1/content_quality` |
| **端点文件名** | snake_case（Python 文件） | `api_keys.py`、`user_auth.py` | ~~`api-keys.py`~~（非法文件名） |

要点：
- **path 与文件名分离**：文件 `api_keys.py`（snake，Python 要求），其内 router `prefix="/api-keys"`（kebab，URL 要求）。不要因为文件是 `_` 就把 path 也写成 `_`。
- **tags 统一英文 kebab、全小写**：不用中文、不用带空格、不用 `_`。中文 tags 会让 OpenAPI 分组在 Swagger 里排序混乱、国际化工具出错。`tags=["api-keys"]` 而非 `tags=["API Keys"]`/`tags=["用量操作"]`。
- **路径参数例外**：`/{user_id}` 的 URL 段名本身是 Python 参数名，用 snake_case（FastAPI 把它同时当 URL 占位符与函数参数）；但**多词资源段**要 kebab：`/api-keys/{key_id}`✅，不是 `/api_keys/{key_id}`❌。
- **`name` 例外**：`name` 是 Python 标识符（给 `request.url_for(name)` 用），用 snake_case，不是 kebab。

```python
# ✅ 正确：文件 snake，path/tags kebab，name snake
# 文件 app/api/v1/endpoints/api_keys.py
router = APIRouter(prefix="/api-keys", tags=["api-keys"])

@router.get("/{key_id}", name="get_api_key")
async def get_api_key(key_id: str, ...): ...

@router.post("", name="create_api_key")           # 集合用空串，不写 "/api-keys"（prefix 已含）
async def create_api_key(...): ...

# ❌ 错误：path/tags 用了 _
router = APIRouter(prefix="/api_keys", tags=["API Keys"])
@router.get("/{key_id}")                           # path 段撞 prefix，且 tags 不规范
```

> ⚠️ **既有偏差声明**：现存服务 tags 混乱（有 `API Keys` 带空格、有 `用量操作`/`订单` 中文、有 `api_keys` 下划线）——这是历史遗留，**不得仿写**。新建/修改端点一律 `tags=["kebab-case"]` 全小写英文。

> 聚合路由前缀见 §5.1：每个服务 `app/api/v1/router.py` 的 `api_router = APIRouter(prefix="/v1/{kebab服务名}")`，`setup` 再挂 `prefix="/api"`，最终 `/api/v1/{kebab服务名}/...`。`{kebab服务名}` 用 `-`（如 `content-quality`），不用 `_`。

### 5.2 Application 层（`app/application/`）—— commands / queries / services 职责三分

**这三个目录是 CQRS + DDD 的职责三分，互补协作，没有"主力/备胎"之分。** 选错归属是架构腐化最常见的源头。先用矩阵定位，再按决策树落地。

应用层统一职责：把 DTO/原始入参翻译成领域意图，协调 repository / cache / clients，管理事务边界，返回 Entity 或结果对象。它**不写领域规则本身**（规则在实体 / 值对象 / 领域服务里）。

#### 5.2.0 职责矩阵

| 目录 | DDD 角色 | 何时进入 | 事务边界 | 典型返回 | 调用关系 |
|---|---|---|---|---|---|
| `commands/` | 写用例处理器（Command Handler） | 改变**单个聚合**状态的用例 | 一个用例 = 一个事务（只改一个聚合实例） | 结果 dataclass（含聚合 Entity） | 由 api 调用，可注入 service |
| `queries/` | 读用例处理器（Query Handler） | 任何**只读**用例 | 无事务 | 为读优化的读模型/结果对象（可不返回完整聚合） | 由 api 调用，可注入 service |
| `services/` | 应用服务（Application Service） | **跨多个聚合**的事务/流程编排；或被 ≥2 用例复用的领域流程；或复杂外部协作 | 管理**跨聚合**事务/流程边界 | Entity / 结果对象 / 无 | 被 command/query 注入复用 |

> 还有第四类：**领域服务（Domain Service）**——不属于任何单一实体、且**无 IO** 的纯领域规则（如跨实体计费、风控判定）。它属于 `domain/`（按需建 `domain/services/`），**不要**放进 `application/services/`。一句话分工：**application service 负责"编排与协调"，domain service 负责"领域规则"。**

#### 5.2.1 决策树（每来一个需求先走一遍）

```
需求来了
├─ 只读数据？ ─────────────────────► queries/   读侧可绕过聚合，直接投影读模型
└─ 改状态？
   ├─ 只涉及单个聚合？ ────────────► commands/  handler 内：取聚合 → 调聚合行为 → 持久化
   ├─ 跨多个聚合 / 多步流程 / 被多用例复用的编排？
   │                              ► services/   写应用服务承载编排，由 command/query 注入调用
   └─ 纯领域规则、跨实体、无 IO？ ──► domain/services/   领域服务
```

通用约束（三者共有）：
- 方法名统一 `execute(...)`（service 可用语义化方法名如 `place(...)`）。
- ❌ 不 import 具体 `SQLxxxRepository`，只依赖 `domain` 的接口类型。
- ❌ 不直接 `httpx`，外部调用走 `clients` 注入的代理。
- ✅ 通过 `@inject` 注入 `domain` 接口、`clients` 代理、`DatabaseManager`。

#### 5.2.2 commands/ —— 写用例处理器

单聚合写用例的天然归属：**取/建聚合 → 调用聚合的领域方法 → 仓储持久化 →（可选）发领域事件**。单聚合用例**不需要 service 中转**，逻辑直接写在 `execute` 里。

```python
# app/application/commands/create_user.py
# ✅ 单聚合写：command 直接注入仓储，逻辑写在 execute（无 service 中转）
from dataclasses import dataclass
from injector import inject

from {pkg}.app.domain.entities.user import User
from {pkg}.app.domain.repositories.user_repository import UserRepository


@dataclass
class CreateUserResult:
    user: User


class CreateUserCommand:
    @inject
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    async def execute(self, name: str, email: str) -> CreateUserResult:
        user = User.create(name=name, email=email)   # 领域工厂方法
        saved = await self.user_repo.create(user)
        return CreateUserResult(user=saved)
```

#### 5.2.3 queries/ —— 读用例处理器

**CQRS 读侧特权：可绕过聚合重建**，直接用仓储的读方法/投影，返回"为这个接口/屏幕定制的读模型"，避免为只读而加载整张聚合图。读模型可以是专门的结果 dataclass，不必是 domain Entity。

```python
# app/application/queries/list_users.py
# ✅ 读侧：返回为列表定制的读模型，不必返回完整聚合
from dataclasses import dataclass
from injector import inject

from {pkg}.app.domain.repositories.user_repository import UserRepository


@dataclass
class UserSummary:            # 仅含列表屏幕需要的字段
    user_id: str
    username: str


@dataclass
class ListUsersResult:
    items: list[UserSummary]
    total: int


class ListUsersQuery:
    @inject
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    async def execute(self, page: int, size: int) -> ListUsersResult:
        users, total = await self.user_repo.list_paged(page, size)
        items = [UserSummary(user_id=u.user_id, username=u.username) for u in users]
        return ListUsersResult(items=items, total=total)
```

#### 5.2.4 services/ —— 应用服务（第一类、不可替代的职责）

`services/` **不是"复用才勉强建"的备胎**。当用例本身就是"跨聚合 / 多步流程"时，由应用服务承载就是 DDD 里它的本职。三类正当场景：

1. **跨聚合事务编排**：一个业务动作要改多个聚合。经典 DDD 经验法则是"一事务一聚合"，跨聚合就交给应用服务统一管事务（或用领域事件做最终一致性）。
2. **被多个用例复用的领域流程**：如"用户开通 = 校验配额 + 落库 + 发欢迎通知"，被注册 / 导入 / 邀请三个 command 共用。
3. **复杂外部协作（防腐）**：按顺序协调多个 `clients` 调用并处理补偿。

```python
# app/application/services/order_placement_service.py
# ✅ 跨聚合（库存 + 订单）事务编排——这是 application service 的本职
from injector import inject
from services_common.database import DatabaseManager

from {pkg}.app.domain.entities.order import Order
from {pkg}.app.domain.repositories.order_repository import OrderRepository
from {pkg}.app.domain.repositories.inventory_repository import InventoryRepository


class OrderPlacementService:
    @inject
    def __init__(self, dm: DatabaseManager, orders: OrderRepository, inventory: InventoryRepository):
        self.dm = dm
        self.orders = orders
        self.inventory = inventory

    async def place(self, user_id: str, sku: str, qty: int) -> Order:
        async with self.dm.transaction():           # 跨聚合统一事务边界
            await self.inventory.reserve(sku, qty)  # 改库存聚合
            order = Order.create(user_id=user_id, sku=sku, qty=qty)
            return await self.orders.create(order)  # 改订单聚合
```

```python
# app/application/commands/place_order.py
# ✅ handler 委托跨聚合编排给 service，但保留自身职责（不是空壳）
from dataclasses import dataclass
from injector import inject

from {pkg}.app.domain.entities.order import Order
from {pkg}.app.application.services.order_placement_service import OrderPlacementService


@dataclass
class PlaceOrderResult:
    order: Order


class PlaceOrderCommand:
    @inject
    def __init__(self, placement: OrderPlacementService):
        self.placement = placement

    async def execute(self, user_id: str, sku: str, qty: int) -> PlaceOrderResult:
        # handler 仍负责：入参→领域意图翻译、结果组装；跨聚合编排委托给 service
        order = await self.placement.place(user_id=user_id, sku=sku, qty=qty)
        return PlaceOrderResult(order=order)
```

> 引入 service 后 command **不是空壳**：它仍负责"入参→领域意图翻译 + 事务/调用入口 + 结果组装"，只把**跨聚合编排**这一段委托出去。

#### 5.2.5 两个对称的反模式（都判不合格）

**反模式 A：单聚合用例硬建 service，handler 沦为空壳转调**

```python
# ❌ create 是单聚合写，却抽出 service 让 command 变空壳，凭空多一层
class UserService:
    async def create(self, name, email):                 # ← 逻辑都在这
        return await self.user_repo.create(User.create(name=name, email=email))

class CreateUserCommand:
    async def execute(self, name, email):                # ← 空壳，无任何编排价值
        return await self.user_service.create(name, email)
# ✅ 单聚合写直接写在 command 里（见 5.2.2）
```

**反模式 B：跨聚合逻辑硬塞进单个 command（或 command 调 command）**

```python
# ❌ command 直接操作多个聚合仓储做跨聚合事务，编排堆积、无法复用
class PlaceOrderCommand:
    async def execute(self, ...):
        await self.inventory_repo.deduct(...)   # 改库存聚合
        await self.order_repo.create(...)       # 改订单聚合
        await self.wallet_repo.charge(...)      # 改钱包聚合 —— 三聚合事务堆在 handler
# ✅ 抽成 OrderPlacementService 统一编排事务，command 注入调用（见 5.2.4）
```

> **正确判据（取代旧"默认不建"）：**
> - **单聚合写** → command 自己干，别建 service。
> - **跨聚合 / 多步流程 / 多用例复用** → 就该建 application service，由 handler 委托。
> - **纯领域规则、无 IO** → domain service（放 `domain/`）。
> - handler 永远保留"事务入口 + 入参翻译 + 结果组装"职责，既不退化为纯转调，也不堆积跨聚合编排。

### 5.3 Domain 层（`app/domain/`）

**最纯净的业务核心**，无任何框架依赖。

- 实体用 `pydantic.BaseModel`，业务规则写成实体方法（如 `update_message`、`can_publish`）。
- 值对象不可变，承载校验规则（非法值在构造时抛领域异常）。
- 仓储/缓存接口用 `ABC + @abstractmethod`，只声明签名，不写实现。
- 领域异常放 `domain/common/exceptions.py`（如 `InvariantViolation`）。
- ❌ 不出现 SQLAlchemy / Redis / httpx / FastAPI / DTO。

#### 5.3.1 仓储标准方法名集合（禁止别名）

Repository 接口方法名统一用下列集合，**禁止** `save`/`insert`/`store`/`upsert` 等别名（避免接口与实现方法名不一致的 AttributeError）：

| 方法 | 语义 | 是否必选 |
|---|---|---|
| `get_by_id(id) -> Optional[Entity]` | 按业务 ID 查 | 必选 |
| `create(entity) -> Entity` | 新建 | 写用例必选 |
| `update(entity) -> Entity` | 更新 | 按需 |
| `delete(id) -> None` | 删除 | 按需 |
| `list_paged(page, size) -> tuple[list[Entity], int]` | 分页列表 | 读用例按需 |

> ⚠️ 模板偏差：`pingpong-service` 的 `create_pong.py` 调了 `pong_repository.save(pong)`，但 `PongRepository`/`SQLPongRepository` 只有 `create`——这是**待修脏模板**的内部矛盾，**不得仿写**。新建仓储一律用 `create`。

#### 5.3.2 只读用例即使调用外部 clients 仍归 queries/

决策树"只读数据 → queries/"分支补充断言：**只读用例即使调用外部 clients（无写副作用、无补偿编排）仍归 `queries/`**，外部调用通过注入 clients 接口完成。只有"**按顺序协调多个外部调用 + 补偿/事务**"才归 `services/`。

> 即：调一次外部服务查数据再返回 = `queries/`；按顺序调 A→B→C 且中间有补偿回滚 = `services/`。不要"只要碰外部就抽 service"（过度设计）。
>
> ⚠️ 模板偏差：`pingpong-service` 的 `get_ping.py`（`PingQuery`）在 query 内构造写用实体、注入了 `AsyncSession`/`Redis` 基础设施具体类型——这是**待修脏模板**，**不得仿写**。query 只应注入 domain 仓储接口 + clients 接口，不应注入 `AsyncSession`/`Redis`（违反 §2 矩阵 application→infrastructure ❌）。

```python
# app/domain/repositories/user_repository.py
from abc import ABC, abstractmethod
from typing import Optional
from {pkg}.app.domain.entities.user import User


class UserRepository(ABC):
    @abstractmethod
    async def get_by_id(self, user_id: str) -> Optional[User]: ...

    @abstractmethod
    async def create(self, user: User) -> User: ...
```

### 5.4 Infrastructure 层（`app/infrastructure/`）

**技术实现层**，实现 domain 接口，封装 DB/Redis/安全。

- 一个聚合一个 `sql_{聚合}_repository.py`，类名 `SQL{聚合}Repository`，继承 domain 接口。
- 必须实现 `_to_entity()` / `_to_model()` 完成 Model↔Entity 转换。
- 一张表一个 `{表}_model.py`，类名 **`{SERVICE_PREFIX_UPPER}{表}Model`**（**全大写的服务前缀** + PascalCase 表名 + `Model`），如 account-service 的 `UserModel` → `ACCUserModel`，pingpong-service（`service_prefix = "pipo"`）的 `PingModel` → `PIPOPingModel`，content-quality-service 的 `UserModel` → `CQALUserModel`。
  - **前缀来源**：`service.metadata` 中的 `service_prefix`（如 `acc` / `pipo` / `cqal`），取其**整体全大写**形式作为类名前缀。
  - **目的**：all-in-one 合并运行时多个服务共享同一 SQLAlchemy `DeclarativeBase`，类名不带服务前缀会冲突；前缀用全大写短码可一眼辨识归属服务、与全小写的表名前缀形成对照。
- **表名必须以 `service_prefix` 为前缀**（全小写），如 `acc_user`、`pipo_ping`。表名前缀（全小写）与类名前缀（全大写）来自同一个 `service_prefix`，仅大小写不同。
- **表名 ↔ 类名对照**：`acc_user` ↔ `ACCUserModel`、`pipo_ping` ↔ `PIPOPingModel`、`cqal_user` ↔ `CQALUserModel`。
- 所有 DB 操作必须 `async/await`，禁止同步。

> **新建/修改服务一律以本规范公式为准**（全大写前缀），不得照抄既有服务的首字母大写或无前缀写法。
>
> 注意 `pingpong` 模板因其 `service_code=0` 占位、ORM 类名为 `PingModel`（无前缀），是"待修脏模板"——复刻新服务时**必须手工**把 `{表}Model` 改为 `{SERVICE_PREFIX_UPPER}{表}Model`（脚手架当前不会自动替换类名，仅替换表名前缀 `pipo_`）。

#### 5.4.1 ORM Model 写法（统一 `Mapped[]` 风格，不得混用 `Column`）

照抄模板，统一用 SQLAlchemy 2.0 的 `Mapped[]` + `mapped_column`，**禁止**和旧式 `Column(...)` 混用。每个**用户业务字段**必须带 `comment`（生成表注释，便于排查）：

```python
# app/infrastructure/persistence/models/user_model.py
from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from services_common.database import BaseModel


class ACCUserModel(BaseModel):
    """User ORM 模型（一表一文件；类名带服务前缀 ACC，表名带 service_prefix 全小写）"""
    __tablename__ = "acc_user"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="自增ID")
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, comment="业务ID")
    username: Mapped[str] = mapped_column(String(64), nullable=False, comment="用户名")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    # ❌ 不要重复声明 created_at / updated_at —— 见下
```

- 继承 `services_common.database.BaseModel`（共享声明基类），**不要**自建 `Base`。
- **`BaseModel` 已统一提供 `created_at`（default=now）与 `updated_at`（default=now, onupdate=now）**，子 Model **不得重复声明**这两个字段（重复声明会覆盖基类列、且漏掉 `onupdate` 自动更新语义）。照抄模板的 `PingModel` 即不重声明——这点模板是对的。
- `comment` 约束**仅适用于用户业务字段**；基类已声明的 `id`/`created_at`/`updated_at` 不强制重写 comment。
- 业务主键用 `user_id`（`generate_id()` 生成的业务 ID），自增 `id` 仅作物理主键/索引。
- 字符串字段必须给长度（`String(36)`），bool/datetime 用对应类型。
- `__tablename__` 与类名前缀来自同一个 `service_prefix`，大小写对应：表 `acc_user` ↔ 类 `ACCUserModel`、表 `pipo_ping` ↔ 类 `PIPOPingModel`。

#### 5.4.2 SQL Repository 写法（session + flush，禁止显式 commit）

照抄模板的三条硬约定：

1. **每个操作独立 `async with self.dm.session() as session:`**——session 由 context 管理提交/回滚，**禁止**在 repository 内显式 `await session.commit()`（会造成与 context 的事务管理冲突）。写操作用 `await session.flush()` 让生成的 ID 回填即可。
2. **`_to_entity` / `_to_model` 是私有方法**，每个 Repository 实现必备，负责 ORM↔Entity 双向转换，**返回值永远是 Entity，绝不返回 ORM Model**。
3. **查询用 `select(...)` + `session.execute(...)`**，取值 `.scalar_one_or_none()` / `.scalar_one()` / `.scalars().all()`；禁止旧式 `session.query(...)`。

```python
# app/infrastructure/persistence/repositories/sql_user_repository.py  —— 照抄此结构
from typing import Optional
from sqlalchemy import select
from injector import inject

from services_common.database import DatabaseManager
from {pkg}.foundation.logging import get_logger
from {pkg}.app.domain.entities.user import User
from {pkg}.app.domain.repositories.user_repository import UserRepository
from {pkg}.app.infrastructure.persistence.models.user_model import ACCUserModel

logger = get_logger(__name__)


class SQLUserRepository(UserRepository):
    """UserRepository 的 SQL 实现"""

    @inject
    def __init__(self, dm: DatabaseManager):
        self.dm = dm

    def _to_entity(self, model: ACCUserModel) -> User:
        return User(user_id=model.user_id, username=model.username,
                    is_active=model.is_active, created_at=model.created_at)

    def _to_model(self, entity: User) -> ACCUserModel:
        return ACCUserModel(user_id=entity.user_id, username=entity.username,
                            is_active=entity.is_active, created_at=entity.created_at)

    async def get_by_id(self, user_id: str) -> Optional[User]:
        async with self.dm.session() as session:
            result = await session.execute(
                select(ACCUserModel).where(ACCUserModel.user_id == user_id)
            )
            model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def create(self, user: User) -> User:
        async with self.dm.session() as session:
            session.add(self._to_model(user))
            await session.flush()        # ✅ flush 回填 ID，不显式 commit
        return user
```

> 跨聚合事务需要显式提交边界时，用 `DatabaseManager.transaction()`（在 application service 里），**不要**在单个 repository 方法里 commit。

#### 5.4.3 跨聚合事务的 session 传递（关键，否则事务不原子）

⚠️ 上面每个 repository 方法都 `async with self.dm.session() as session:`——这是**单聚合写**的约定（每方法一事务，session 退出即隐式 commit）。但**跨聚合事务**（§5.2.4 application service 编排）若直接调多个 repo 方法，每个 repo 会各开自己的 session 独立提交，**外层 `dm.transaction()` 不原子**。

**跨聚合事务必须让各 repository 复用同一个 session**。标准模式：repository 提供"接收外部 session"的重载入口，application service 在 `transaction()` 内把 session 传进去：

```python
# infrastructure/persistence/repositories/sql_order_repository.py
class SQLOrderRepository(OrderRepository):
    @inject
    def __init__(self, dm: DatabaseManager):
        self.dm = dm

    async def create(self, order: Order) -> Order:                  # 单聚合写：自管 session
        async with self.dm.session() as session:
            session.add(self._to_model(order))
            await session.flush()
        return order

    async def create_in_session(self, order: Order, session: AsyncSession) -> Order:   # 跨聚合：复用外层 session
        session.add(self._to_model(order))
        await session.flush()
        return order


# application/services/order_placement_service.py
class OrderPlacementService:
    @inject
    def __init__(self, dm: DatabaseManager, orders: OrderRepository, inventory: InventoryRepository):
        self.dm = dm; self.orders = orders; self.inventory = inventory

    async def place(self, user_id: str, sku: str, qty: int) -> Order:
        async with self.dm.transaction() as session:        # ← 一个事务、一个 session
            await self.inventory.reserve_in_session(sku, qty, session)   # 复用 session
            order = Order.create(user_id=user_id, sku=sku, qty=qty)
            return await self.orders.create_in_session(order, session)   # 复用 session
```

约定：
- 单聚合写：调 `repo.create(entity)`（自管 session）。
- 跨聚合事务：在 application service 的 `async with dm.transaction() as session:` 内，调各 repo 的 `xxx_in_session(entity, session=session)` 重载。
- **禁止**在 `transaction()` 内再调 `repo.create()`（会另开 session 独立提交，破坏原子性）。
- 若 `services_common` 提供了支持共享 session 的 repository 基类约定，优先复用；否则按上述 `xxx_in_session` 模式。

> 如果你的用例只改一个聚合，根本不需要这节——直接 `repo.create()` 即可。只有"一个业务动作改多个聚合"才需要 session 传递。

```python
# app/infrastructure/persistence/models/user_model.py
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from services_common.database import BaseModel


class ACCUserModel(BaseModel):        # ← 类名带服务前缀（acc → ACC 全大写）
    __tablename__ = "acc_user"        # ← 表名带 service_prefix（全小写）

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="自增ID")
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, comment="业务ID")
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="姓名")
```

---

## 6. 依赖注入规范

### 6.1 容器与注册

- `foundation/container.py` 管理全局 `Injector`（`set_injector` / `get_injector`）。
- 每层在各自 `modules.py` 注册绑定：`DomainModule`、`ApplicationModule`、`InfrastructureModule`、`ClientsModule`。
- 接口 → 实现 的绑定一律写在 `InfrastructureModule` / `ClientsModule`。

### 6.1.1 `modules.py` 的四条硬约定（AI 最易跑偏处）

照抄 pingpong-service 模板的写法，不得变形：

1. **import 一律写在 `configure(self, binder)` 方法体内**（延迟导入），**禁止**把 `from {pkg}.app.domain... import XxxRepository` 放到模块顶部。原因：模块加载时 injector 尚未装配，顶层 import 会触发跨层循环导入。模板五个 `modules.py` 全部如此。
2. **绑定语句统一** `binder.bind(接口, to=实现, scope=...)`，`scope` 取值见 §6.1.2 判据（不得省略 `scope=`）。
3. **一行一绑定**，每个绑定前用注释标明类别（`# Repository` / `# Cache` / `# Client` 等），顺序：Cache → Repository（InfrastructureModule）；command → query → service（ApplicationModule）。
4. **接口在 domain/clients，实现在 infrastructure/clients**，绑定即"接口→实现"映射。`DomainModule.configure` 保持 `pass`（domain 无具体实现要绑）。

```python
# app/infrastructure/modules.py  —— 照抄此结构
from injector import Module, Binder


class InfrastructureModule(Module):
    """模块的依赖注入"""
    def configure(self, binder: Binder):
        # Cache
        from {pkg}.app.domain.caches.{域}_cache import {域}Cache
        from {pkg}.app.infrastructure.caches.{域}_redis_cache import {域}RedisCache
        binder.bind({域}Cache, to={域}RedisCache, scope=None)

        # Repository
        from {pkg}.app.domain.repositories.{聚合}_repository import {聚合}Repository
        from {pkg}.app.infrastructure.persistence.repositories.sql_{聚合}_repository import SQL{聚合}Repository
        binder.bind({聚合}Repository, to=SQL{聚合}Repository, scope=None)
```

```python
# app/application/modules.py
from injector import Module, Binder


class ApplicationModule(Module):
    """模块的依赖注入"""
    def configure(self, binder: Binder):
        from {pkg}.app.application.commands.create_{聚合} import Create{聚合}Command
        binder.bind(Create{聚合}Command, to=Create{聚合}Command, scope=None)

        from {pkg}.app.application.queries.get_{聚合} import Get{聚合}Query
        binder.bind(Get{聚合}Query, to=Get{聚合}Query, scope=None)

        # Service（无跨聚合编排则不注册）
        # from {pkg}.app.application.services.{域}_service import {域}Service
        # binder.bind({域}Service, to={域}Service, scope=None)
```

```python
# app/domain/modules.py  —— 永远是空 pass，不要往里塞绑定
from injector import Module, Binder


class DomainModule(Module):
    """模块的依赖注入"""
    def configure(self, binder: Binder):
        pass
```

> application clients 的 `ClientsModule` 同理：内部服务绑 `接口→APIProxy`，第三方绑 `接口→Remote实现`，import 都在方法体内（见 §7.4）。

### 6.1.2 `scope` 取值判据（None vs singleton，AI 高频误判处）

`scope` 不是只能 `None`。按下表判据选择，**同一 `modules.py` 内不得无注释地混用**：

| `scope` | 语义 | 何时用 | 典型对象 |
|---|---|---|---|
| `None`（transient） | 每次 `injector.get(...)` 新建实例 | **默认值**：无状态、轻量、构造廉价的业务对象 | Command、Query、应用 Service、SQL Repository（若其依赖每次新建无害） |
| `singleton` | 全进程单例 | 持有**重资源**或需**跨请求共享状态** | 持有 DB 连接池的 DatabaseManager/Repository、RedisManager、Settings、带内部缓存的 application service |

判据口诀：**"每次 new 会不会浪费/出错？"** 会（重资源、有状态缓存）→ `singleton`；不会（无状态用例）→ `None`。

```python
binder.bind(CreateUserCommand, to=CreateUserCommand, scope=None)          # 无状态用例 → None
binder.bind(UserRepository, to=SQLUserRepository, scope=singleton)         # 持有连接池 → singleton
binder.bind(SomeCachingService, to=SomeCachingService, scope=singleton)    # 内部缓存 → singleton
```

> 先 `from injector import singleton` 再用。生产服务（content-ops、rag 等）已大量使用 `scope=singleton` 给重资源对象，照此判据写即可，不要一律 `None`。

### 6.1.3 `BuiltinModule` 与装配顺序（基础设施怎么进容器）

四层 `modules.py` 只绑业务类。**基础设施对象**（`Settings`/`DatabaseManager`/`RedisManager`/`AsyncEngine`/`AsyncSession`/`LogManager`）由 `main.py` 的 `setup()` 内联定义的 `BuiltinModule` 注册，**四层 modules.py 不得重复绑这些类型**（重复绑会冲突）。

```python
# main.py 的 setup() 内（不在 modules.py 里）
class BuiltinModule(Module):
    def configure(self, binder: Binder):
        binder.bind(Settings, to=lambda: _settings, scope=None)            # λ provider 注入已构造单例
        binder.bind(RedisManager, to=lambda: _redis_manager, scope=None)
        binder.bind(DatabaseManager, to=lambda: _db_manager, scope=None)
        binder.bind(AsyncEngine, to=lambda: _db_manager.engine, scope=None)
        binder.bind(AsyncSession, to=lambda: _db_manager.session_maker, scope=None)
        binder.bind(LogManager, to=LogManager, scope=None)
```

- `to=lambda: instance` 是合法的 provider 写法（注入"已构造好的单例对象"），与 `to=SomeClass`（让 injector 构造）不同，二者按需选用。
- **装配顺序固定**：`Injector([BuiltinModule, ClientsModule, DomainModule, ApplicationModule, InfrastructureModule])`。injector 绑定语义是"后注册覆盖先注册"，故基础设施（Builtin）先注册、业务层后注册；**禁止**在业务 modules.py 重复绑定 BuiltinModule 已绑的基础类型。
- 新增"纯基础设施共享类型"加到 `BuiltinModule`，不加进业务 modules.py。

### 6.2 新增依赖必做

新增 Repository / Cache / Client / Command / Query / Service 后，**必须**在对应 `modules.py` 增加绑定。未注册即视为未完成任务。

### 6.3 在端点中取用

```python
def get_user_query() -> GetUserQuery:
    return get_injector().get(GetUserQuery)
```

---

## 7. 外部服务调用规范（`clients/`）

### 7.1 目录结构（一外部依赖一目录）

```
clients/
├── modules.py                    # DI 注册
├── github/                       # 仅 HTTP，无模式切换
│   ├── __init__.py               # 仅包标识（docstring），不写导出逻辑
│   ├── interface.py              # 抽象接口 (ABC)
│   ├── schemas.py                # Client Schema (Pydantic)
│   └── api_proxy.py              # 代理类（直接 HTTP）
└── {内部服务名}/                 # services 内部服务，需双模式
    ├── __init__.py               # 仅包标识（docstring），不写导出逻辑
    ├── interface.py              # 抽象接口 (ABC)
    ├── schemas.py                # Client Schema (Pydantic)
    ├── remote_api.py             # Standalone：远程 HTTP
    ├── local_api.py              # All-In-One：本地直调
    └── api_proxy.py              # 代理：按 MODEL 切换 local/remote
```

> ⚠️ **import 约定（统一为"完整模块路径"，禁止依赖 `__init__.py` 导出）**：
> `clients/modules.py` 与 application 一律从**具体模块文件**直接 import，例如
> `from {pkg}.clients.asset_service.api_proxy import AssetServiceAPIProxy`、
> `from {pkg}.clients.asset_service.interface import AssetService`。
> **不要**写成 `from {pkg}.clients.asset_service import AssetServiceAPIProxy`（依赖包根导出）。
> 这样 `__init__.py` 保持空（只留 docstring），避免"空 `__init__` 导致注册失败"或"循环导入"。

### 7.2 必须返回 Client Schema，禁止裸 dict（重点）

- `interface.py` 的每个方法**必须标注 Pydantic 返回类型**（无返回值用 `-> None`）。
- `remote_api.py` 拿到 HTTP 响应后**必须 `XxxSchema(**data)` 转换再返回**，禁止 `return resp.json()`、禁止 `return {...}`。
- `local_api.py` 与 `remote_api.py` 返回类型必须完全一致（里氏替换）。
- `api_proxy.py` 的方法签名/返回类型必须与 `interface.py` 完全一致。

```python
# clients/account_service/interface.py
from abc import ABC, abstractmethod
from {pkg}.clients.account_service.schemas import UserInfo


class AccountService(ABC):
    @abstractmethod
    async def get_user_by_id(self, user_id: str) -> UserInfo: ...


# clients/account_service/schemas.py
from pydantic import BaseModel


class UserInfo(BaseModel):
    user_id: str
    name: str
    email: str | None = None


# clients/account_service/remote_api.py
import httpx
from {pkg}.clients.account_service.interface import AccountService
from {pkg}.clients.account_service.schemas import UserInfo


class RemoteAccountService(AccountService):
    def __init__(self, base_url: str):
        self.base_url = base_url

    async def get_user_by_id(self, user_id: str) -> UserInfo:
        async with httpx.AsyncClient(base_url=self.base_url) as client:
            resp = await client.get(f"/api/v1/users/{user_id}")
            data = resp.json().get("data", {})
            return UserInfo(**data)          # ✅ 必须转 schema 返回


# clients/account_service/api_proxy.py
from injector import inject
from {pkg}.clients.account_service.interface import AccountService
from {pkg}.clients.account_service.schemas import UserInfo
from {pkg}.foundation.config import Settings


class AccountServiceAPIProxy(AccountService):
    @inject
    def __init__(self, setting: Settings):
        self.proxy: AccountService
        if setting.MODEL == "all-in-one":
            from {pkg}.clients.account_service.local_api import LocalAccountService
            self.proxy = LocalAccountService()
        else:
            from {pkg}.clients.account_service.remote_api import RemoteAccountService
            self.proxy = RemoteAccountService(base_url=setting.ACCOUNT_SERVICE_URL)

    async def get_user_by_id(self, user_id: str) -> UserInfo:
        return await self.proxy.get_user_by_id(user_id)
```

### 7.3 local / remote 模式要求（第三方"无需 local/remote"≠"无 interface"）

- **services 内部服务**（如 account/asset/commercial）：必须同时实现 `local_api` 与 `remote_api`，并由 `api_proxy` 按 `setting.MODEL` 切换。
- **services 外部第三方**（如 github、aliyun、feishu）：无需 `local_api`/`remote_api` 双模式（无 in-process 等价物），但仍**必须**有 `interface.py`（ABC）+ `schemas.py`（Client Schema）+ `api_proxy.py`（直接 HTTP 实现）三件套。**"只需 api_proxy"是指省去 local/remote 切换，不是省去 interface/schemas。**
- **所有 client（含第三方）的方法必须返回 `schemas.py` 的 Pydantic 模型**，禁止返回 `str`/`dict`/`resp.json()`。

> ⚠️ **模板偏差声明**：`pingpong-service` 的 `clients/github/` 当前只有单文件 `oauth.py`、无 `interface.py`/`schemas.py`、`oauth_request()` 返回裸 `str`、DI 绑具体类 `GithubOauthAPIClient`——这是**待修脏模板**，**不得仿写**。新建第三方 client 必须按三件套（`interface.py`+`schemas.py`+`api_proxy.py`）补全，DI 绑接口。

### 7.4 注册（绑接口，不绑具体类；模板偏差标注）

**硬约束**：`ClientsModule` 一律 **绑"接口 → 实现"**，application 一律注入**接口类型**（ABC），由 DI 决定实现。`scope` 按 §6.1.2 判据。

```python
# clients/modules.py
from injector import Module, Binder


class ClientsModule(Module):
    def configure(self, binder: Binder):
        # 内部服务：绑定"接口 → 代理"，从具体模块文件 import
        from {pkg}.clients.account_service.interface import AccountService
        from {pkg}.clients.account_service.api_proxy import AccountServiceAPIProxy
        binder.bind(AccountService, to=AccountServiceAPIProxy, scope=None)

        # 第三方（仅 remote）：绑定"接口 → remote 实现"
        from {pkg}.clients.feishu.interface import FeishuClient
        from {pkg}.clients.feishu.remote_api import RemoteFeishuClient
        binder.bind(FeishuClient, to=RemoteFeishuClient, scope=None)
```

> application 注入时依赖**接口**类型（`AccountService`），而非具体代理类，符合依赖倒置；由 DI 决定注入哪个实现，切换实现无需改 application。

> ⚠️ **模板偏差声明**：`pingpong-service` 的 `clients/modules.py` 当前绑的是具体类（`bind(OtherServiceAPIProxy, to=OtherServiceAPIProxy)`、`bind(GithubOauthAPIClient, to=GithubOauthAPIClient)`），且 `get_ping.py` 也注入具体代理类而非 `UserService` 接口——这是**待修脏模板**，**不得仿写**。改写时改为绑接口（`bind(UserService, to=OtherServiceAPIProxy)`），application 注入 `UserService`。生产服务 `account-service` 的 `clients/modules.py` 已是正确的"绑接口"写法（`bind(FeishuClient, to=RemoteFeishuClient)`、`bind(AssetService, to=AssetServiceAPIProxy)`），可作对照。

#### 7.4.1 interface / 代理 / remote-local 类名同源规则

client 套件的目录名与各类名必须**同源**于同一个 `{服务}` 根，不得分裂：

| 命名对象 | 规则 | 以 `account_service` 为例 |
|---|---|---|
| 目录名 | `{服务 snake}_service/`（内部）或 `{第三方 snake}/`（第三方） | `account_service/` |
| interface 类 | `{Pascal 服务}Service`（内部）或 `{Pascal 第三方}Client`（第三方） | `AccountService` |
| APIProxy 类 | `{Pascal 服务}ServiceAPIProxy` | `AccountServiceAPIProxy` |
| Remote 实现 | `Remote{Pascal 服务}Service` | `RemoteAccountService` |
| Local 实现 | `Local{Pascal 服务}Service` | `LocalAccountService` |

> ⚠️ **模板偏差声明**：`pingpong-service` 的 `clients/other_service/` 里目录叫 `other_service`、interface 却叫 `UserService`、代理叫 `OtherServiceAPIProxy`——目录名/接口名/代理名三者不同源，这是**待修脏模板**，**不得仿写**。改写时把四处统一到同一个服务根（如全按 `account_service`/`AccountService`/`AccountServiceAPIProxy` 派生）。

### 7.5 clients 禁止事项

- ❌ 在 `app/api`、`app/application`、`app/domain`、`app/infrastructure` 中直接 `httpx`/`requests`。
- ❌ `clients` 方法返回裸 `dict` / `resp.json()`。
- ❌ 跳过 `interface` 直接在 application 里 `new` 一个 `RemoteXxx`。
- ❌ 在 `domain` 中出现外部服务 URL / API Key。

---

## 8. 配置管理规范（`foundation/config.py`）

```python
from functools import lru_cache
from services_common.config import AppSettings, DatabaseSettings, RedisSettings


class Settings(AppSettings, DatabaseSettings, RedisSettings):
    PORT: int = 8001
    REDIS_PREFIX: str = "MyService"
    # 外部服务地址：{大写服务名}_SERVICE_URL
    ACCOUNT_SERVICE_URL: str = "http://localhost:8001"
    # 业务自定义配置必须加服务前缀
    ACC_XXXX: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- 外部服务地址命名统一 `{服务}_SERVICE_URL`。
- 业务自定义配置项必须加服务前缀（与 `service_prefix` 一致），避免 all-in-one 合并时冲突。

---

## 9. 共享模块使用（`services_common`）

通用能力一律复用，禁止各服务自行实现：

- 数据库：`services_common.database.DatabaseManager` / `BaseModel`
- Redis：`services_common.redis.RedisManager`
- 日志：`services_common.logging.Logger`
- 配置基类：`services_common.config.{AppSettings,DatabaseSettings,RedisSettings}`
- 统一响应：`services_common.{success, created, DataResponse}`（所有响应构建函数均支持 `biz_code` 参数）
- 业务码工具：`services_common.biz_code.{BizCategory, make_biz_code, parse_biz_code}`（仅编码规则和工具，不含服务枚举表）
- 异常处理 / 中间件：`services_common.exception_handlers` / `services_common.middleware`

> ⚠️ `services_common` 只提供 biz_code 的**编码规则和工具函数**（`BizCategory` 枚举 + `make_biz_code` / `parse_biz_code`），**不包含任何服务的业务码枚举表**。各服务在自己的 `foundation/biz_code.py` 中声明 `SERVICE_CODE` 和 `BizCode(IntEnum)`，避免依赖倒置。

---

## 10. 命名规范汇总

| 对象 | 规则 | 示例 |
|---|---|---|
| 服务目录 | `{名}-service`（短横线） | `account-service` |
| 包名 | `{名}_service`（下划线） | `account_service` |
| 实体类 | 名词单数 PascalCase | `User`, `Order` |
| 仓储接口 | `{聚合}Repository` | `UserRepository` |
| 仓储实现 | `SQL{聚合}Repository` | `SQLUserRepository` |
| ORM 模型类 | `{SERVICE_PREFIX_UPPER}{表}Model` | `ACCUserModel` |
| ORM 表名 | `{service_prefix}_{表}` | `acc_user` |
| Command | `{动词}{名词}Command` | `CreateUserCommand` |
| Query | `Get/List{名词}Query` | `GetUserQuery` |
| 应用服务 | `{域}Service` | `UserService` |
| Client 代理 | `{服务}ServiceAPIProxy` | `AccountServiceAPIProxy` |
| 路由 path/tags/聚合 prefix | kebab-case（`-`），tags 全小写英文 | `/api-keys`、`tags=["api-keys"]`、`/v1/content-quality` |
| 路由 `name`/`operation_id` | snake_case（Python 标识符） | `name="get_user"` |
| 端点文件名 | snake_case（Python 文件） | `api_keys.py` |
| 日志 operation | `{域}.{对象}.{动作}[.success/.error]` | `user.get.error` |
| 服务码 | 1-89 整数，全局唯一，写入 `service.metadata` 的 `service_code` 字段 | `1`（account）、`7`（content） |
| 服务码（模板） | `0` 预留给 pingpong 模板占位，实际服务不可使用 | `0`（pingpong） |
| 业务码 | 8 位整数 `1SS DDDEEE`，由 `make_biz_code(SERVICE_CODE, BizCategory, seq)` 生成 | `11002001`（account 认证错误） |

---

## 11. 禁止事项（汇总）

1. ❌ 跨边界传裸 `dict` 作为契约（含 clients 返回、层间返回、端点返回）。
2. ❌ 同层多类别塞一个文件（多个 Repository/Service/Model 混写）。
3. ❌ api 层 import infrastructure 或 ORM Model。
4. ❌ application import 具体仓储/缓存实现（只依赖 domain 接口）。
5. ❌ domain 依赖 SQLAlchemy/Redis/httpx/FastAPI/DTO。
6. ❌ repository 把 ORM Model 返回给 application。
7. ❌ 端点写业务逻辑、跳过 command/query 直接操作数据库。
8. ❌ **应用层职责错位**（按 §5.2 决策树判定）：单聚合写用例硬抽 service 让 command 沦为空壳转调；或反过来把跨聚合/多步流程编排硬塞进单个 command。command/query 永远保留"事务入口+入参翻译+结果组装"职责，跨聚合编排交给 application service，纯领域规则交给 domain service。
9. ❌ 在 `app/` 中直接 `httpx`/`requests` 调外部（必须走 clients）。
10. ❌ 同步数据库操作（必须 async/await）。
11. ❌ 新增依赖后忘记在 `modules.py` 注册。
12. ❌ 在 `demo`/模板文件上直接写业务实现（应新建对应业务文件）。
13. ❌ 新增第三方依赖未在 `pyproject.toml` 声明版本。
14. ❌ **ORM Model 类名不带服务前缀**：必须 `class {SERVICE_PREFIX_UPPER}{表}Model`（如 `ACCUserModel`），表名必须 `{service_prefix}_{表}`（如 `acc_user`）。不带前缀会导致 all-in-one 合并时类名/表名冲突。
15. ❌ **外部服务/外部接口调用写进 `infrastructure/`**：调别的服务/第三方（httpx、SDK）只能放 `clients/`；`infrastructure/` 只适配本服务自己的 DB/Redis。见 §2.1。`infrastructure/` 内出现 `httpx` / 调外部 URL 即为不合格。
16. ❌ **`infrastructure` 与 `clients` 互相 import**：二者平行，不互相依赖，只在 application 层协作。
17. ❌ **`modules.py` 顶层 import 业务类 / 缺 `scope=None` / 把 domain 接口→实现的绑定写进 DomainModule**：见 §6.1.1 四条硬约定。
18. ❌ **重命名脚手架生成的目录或顶层包**：`generate-service` 后包名/前缀/import 根已正确，AI 不得改名，只在 `app/` 内按业务新增文件。
19. ❌ **HTTP 路由用 `_` 连接**：path / tags / 聚合 prefix 一律 kebab-case（`/api-keys`、`tags=["api-keys"]`、`/v1/content-quality`）。仅 Python 文件名/类名/函数名/name 标识符用 snake/Pascal。见 §5.1.1。tags 不得用中文或带空格。

---

## 12. 开发流程检查清单（提交前逐条核对）

**结构与分层**
- [ ] 新文件放在正确的层目录，无跨层错放
- [ ] 一文件一职责，未把多类别塞同一文件
- [ ] 依赖方向符合 §2 矩阵，无反向 import
- [ ] **每个写用例在 `commands/` 有 Command 类、每个读用例在 `queries/` 有 Query 类，逻辑写在其中**
- [ ] **应用层归属符合 §5.2 决策树**：只读→queries；单聚合写→commands（逻辑直接写在 execute）；跨聚合/多步/多用例复用→services（command 委托但不退化为空壳）；纯领域规则无 IO→domain service
- [ ] **命名按 §0.1 占位符表推导**（`{pkg}`/`{SERVICE_PREFIX_UPPER}` 全大写前缀/表名前缀），未重命名脚手架生成的目录或顶层包
- [ ] **demo 代码已清理**：无 `pong`/`ping`/`PAP`/`pp_demo`/`biz_code_test` 残留，删除的类在 `modules.py` 同步移除绑定（§0.2）

**数据载体**
- [ ] 层间/clients/端点均未返回裸 `dict`
- [ ] DTO 在 `schemas/`，Entity 在 `domain/`，Model 仅在 infrastructure
- [ ] Repository 实现含 `_to_entity` / `_to_model`，返回 Entity

**clients**
- [ ] `interface.py` 方法均标注 Pydantic 返回类型
- [ ] `remote_api` 将响应转 schema 再返回
- [ ] 内部服务实现了 local + remote 双模式
- [ ] DI 用"接口 → 实现"绑定，import 走完整模块路径（不依赖 `__init__` 导出）

**DI 与配置**
- [ ] 新增依赖已在对应 `modules.py` 注册
- [ ] `modules.py` 的 import 在 `configure()` 方法体内，绑定用 `bind(接口, to=实现, scope=None)`，`DomainModule` 为空 `pass`（§6.1.1）
- [ ] 表名带 `service_prefix`（全小写）；**ORM 类名带服务前缀**（`ACCUserModel`，全大写前缀）；自定义配置带服务前缀
- [ ] **外部服务调用在 `clients/`，不在 `infrastructure/`；二者不互相 import**（§2.1）
- [ ] ORM Model 统一 `Mapped[]` 风格，字段带 `comment`（§5.4.1）
- [ ] Repository 用 `async with self.dm.session()` + `flush()`，无显式 `commit`；返回 Entity（§5.4.2）
- [ ] 新增第三方依赖已写入 `pyproject.toml`

**通用**
- [ ] 复用 `services_common`，未重复造轮子
- [ ] DB 操作全为 async；命名符合 §10
- [ ] **每个领域/应用异常都绑定了 BizCode 枚举成员**（非默认 0）
- [ ] **BizCode 枚举每个成员都有中文注释描述具体业务问题**
- [ ] **新服务已在 `foundation/biz_code.py` 声明 `SERVICE_CODE`**（与 `service.metadata` 中的 `service_code` 一致）
- [ ] **HTTP 路由命名合规**（§5.1.1）：path/tags/聚合 prefix 用 kebab（`/api-keys`、`tags=["api-keys"]`、`/v1/{kebab}`）；文件名/name 用 snake；tags 全小写英文无中文无空格

---

## 13. 业务码规范（biz_code）

### 13.1 编码结构

biz_code 为 8 位整数，结构如下：

```
biz_code = 1 SS DDD EEE
           │ │  │   └─ 3位 业务序号 (001-999)
           │ │  └──── 3位 业务大类 (BizCategory 枚举值)
           │ └──────── 2位 服务编号 (00-89, 00=模板/公共占位)
           └────────── 固定前缀 1（保证始终 8 位数）
```

固定前缀 `1` 确保所有 biz_code 都是完整的 8 位整数（10,000,000 ~ 99,099,999），
避免 service_code 较小时因整数前导零丢失导致位数不足。

- **SS（服务编号）**：1-89 为实际服务，0 预留给 pingpong 模板和 `services_common` 公共异常兜底
- **DDD（业务大类）**：由 `BizCategory(IntEnum)` 统一定义，所有服务共用
- **EEE（业务序号）**：每个服务在同一个 `BizCategory` 下从 1 递增

> ⚠️ **上面的 8 位结构只用于"错误响应"。成功响应的 biz_code 是 `0`**，不是 8 位。`0` 是"通用成功"的特殊占位（不复用 `1SSDDDEEE` 结构，成功无需区分服务/大类）。`make_biz_code(..., BizCategory.SUCCESS, 0)` 算出的 8 位值（如 `12000000`）只在 `BizCode.SUCCESS` 枚举成员里声明、供解析/标识用，**不进成功响应**——`success()` 默认输出 `0`。一句话：**成功 = `0`；错误 = 8 位 `1SSDDDEEE`（异常透传）。** 详见 §13.6。

### 13.2 服务编号分配

| 规则 | 说明 |
|------|------|
| 分配方式 | 由 `generate-service` 脚本在创建服务时分配，写入 `service.metadata` 的 `service_code` 字段 |
| 冲突检测 | 脚本自动检测重复（与 port、prefix 检测逻辑一致） |
| 模板占位 | pingpong 模板使用 `SERVICE_CODE = 0`，脚本生成新服务时自动替换为实际编号（1-89） |
| 公共兜底 | `services_common.exceptions` 中的公共异常使用 `_COMMON_SERVICE_CODE = 0` |
| 取值范围 | 0 = 模板/公共占位，1-89 = 实际服务，固定前缀 `1` 保证 biz_code 始终 8 位整数 |

当前已分配的服务编号见各 `service.metadata` 文件，新建服务从 20 开始递增。

### 13.3 BizCategory 业务大类

| 枚举值 | 语义 | 典型场景 |
|--------|------|----------|
| `SUCCESS = 0` | 通用成功 | 请求处理成功 |
| `VALIDATION = 1` | 参数校验类 | 必填缺失、格式错误、枚举非法 |
| `AUTH = 2` | 认证授权类 | 未登录、token 失效、无权限 |
| `NOT_FOUND = 3` | 资源不存在类 | 实体未找到 |
| `CONFLICT = 4` | 资源冲突类 | 重复创建、状态冲突 |
| `QUOTA = 5` | 配额/限额类 | 余额不足、次数用尽、限流 |
| `BUSINESS_RULE = 6` | 业务规则类 | 领域校验不通过（如订单状态不允许） |
| `EXTERNAL = 7` | 外部依赖类 | 下游服务调用失败、第三方 API 异常 |
| `CONSISTENCY = 8` | 数据一致性类 | 并发冲突、版本号过期 |
| `CONTENT_MEDIA = 9` | 媒体/内容类 | 内容审核不通过、格式不支持 |
| `PAYMENT_TXN = 10` | 支付/交易类 | 支付失败、退款异常 |
| `LLM_AI = 11` | LLM/AI 类 | 模型超时、内容生成失败 |
| `SYSTEM = 99` | 系统内部错误 | 未分类异常兜底 |

> 新增业务大类需修改 `services_common.biz_code.BizCategory`，属全局变更，需团队评审。

### 13.4 各服务的 BizCode 定义（强制）

每个服务**必须**在 `foundation/biz_code.py` 中定义自己的业务码枚举：

```python
# foundation/biz_code.py
from enum import IntEnum
from services_common.biz_code import BizCategory, make_biz_code

SERVICE_CODE = 7  # content-service 的服务编号，与 service.metadata 中的 service_code 一致


class BizCode(IntEnum):
    """Content 服务业务码枚举

    每个成员必须附带中文注释，描述具体的业务场景或问题。
    """

    # ── 通用成功 ──
    SUCCESS = make_biz_code(SERVICE_CODE, BizCategory.SUCCESS, 0)           # 请求处理成功

    # ── 资源不存在类 ──
    CONTENT_NOT_FOUND = make_biz_code(SERVICE_CODE, BizCategory.NOT_FOUND, 1)  # 内容记录不存在
    CONTENT_DELETED = make_biz_code(SERVICE_CODE, BizCategory.NOT_FOUND, 2)    # 内容已被删除

    # ── 业务规则类 ──
    CONTENT_PUBLISHED = make_biz_code(SERVICE_CODE, BizCategory.BUSINESS_RULE, 1)  # 内容已发布，不可重复发布
```

**硬约束**：
1. 每个枚举成员**必须有中文注释**，描述具体的业务场景或问题
2. `SERVICE_CODE` 的值必须与 `service.metadata` 中的 `service_code` 一致
3. 新增业务码时按 `BizCategory` 分组，序号在同一大类内从 1 递增
4. 禁止直接手写数字（如 `AUTH_ERROR = 7020001`），必须通过 `make_biz_code()` 生成

#### 13.4.1 序号分配规则（消除歧义）

序号**按 BizCategory 大类独立计数**，每个大类内从 1 递增，**不同大类互不影响**。即 `NOT_FOUND` 的 1/2/3 与 `CONFLICT` 的 1/2/3 是各自独立的，不冲突。照搬模板的分组排版样式：

```python
class BizCode(IntEnum):
    # ── 通用成功 ──
    SUCCESS = make_biz_code(SERVICE_CODE, BizCategory.SUCCESS, 0)            # 请求处理成功

    # ── 参数校验类 ──
    VALIDATION_FAILED = make_biz_code(SERVICE_CODE, BizCategory.VALIDATION, 1)  # 请求参数校验不通过

    # ── 认证授权类 ──
    AUTH_PASSWORD_ERROR = make_biz_code(SERVICE_CODE, BizCategory.AUTH, 1)      # 用户名或密码错误
    AUTH_TOKEN_INVALID = make_biz_code(SERVICE_CODE, BizCategory.AUTH, 2)       # token 格式非法

    # ── 资源不存在类 ──
    USER_NOT_FOUND = make_biz_code(SERVICE_CODE, BizCategory.NOT_FOUND, 1)      # 用户不存在
    ORDER_NOT_FOUND = make_biz_code(SERVICE_CODE, BizCategory.NOT_FOUND, 2)     # 订单不存在

    # ── 资源冲突类 ──
    USER_ALREADY_EXISTS = make_biz_code(SERVICE_CODE, BizCategory.CONFLICT, 1)  # 用户已存在
    ORDER_DUPLICATE = make_biz_code(SERVICE_CODE, BizCategory.CONFLICT, 2)      # 订单重复创建
```

- `SUCCESS` 固定用序号 `0`。
- 其余大类从 `1` 起，**不跨大类续号**（不要写成 NOT_FOUND 用 1/2、CONFLICT 接着用 3/4）。
- 成员名 = `{业务对象}_{状态}` 或 `{业务动作}_{结果}`，UPPER_SNAKE，语义自解释。
- 新增成员时先用 grep 确认同大类内最大序号，从下一个续号；禁止复用已删成员的序号。

### 13.5 异常绑定 BizCode（强制）

所有领域异常和应用异常**必须**绑定 BizCode 枚举成员：

```python
# ✅ 正确：异常携带 biz_code
class ContentNotFoundException(BaseDomainException):
    """内容记录不存在 - 查询的实体在数据库中未找到"""

    def __init__(self, content_id: str):
        super().__init__(
            f"content not found: {content_id}",
            code="CONTENT_NOT_FOUND",
            biz_code=BizCode.CONTENT_NOT_FOUND,
        )

# ❌ 错误：未绑定 biz_code，异常处理器只能用默认值 0
class ContentNotFoundException(BaseDomainException):
    def __init__(self, content_id: str):
        super().__init__(f"content not found: {content_id}", code="CONTENT_NOT_FOUND")
```

### 13.6 响应中的 biz_code

- **成功响应**：`biz_code` 固定为 `0`（表示"通用成功"）。`services_common.response.success()`/`created()` 的 `biz_code` 默认值就是 `0`，**直接用 `success(data=...)` 即可，不要传 `biz_code=BizCode.SUCCESS`**。
  - `0` 是 biz_code 的特殊占位，**不**走 8 位 `1SSDDDEEE` 结构——它不代表某个服务，只代表"通用的成功"。
  - 成功响应无需区分"哪个服务"的成功，故不复用 8 位定位能力；真正需要精确定位的是**错误**响应。
- **错误响应**：由异常处理器自动从 `exc.biz_code` 透传到 `ErrorResponse.biz_code`（**必是 8 位 `1SSDDDEEE`**），无需手动构建。
- **直接构建错误响应**（endpoint 内 catch 后自定义）：`not_found(biz_code=BizCode.CONTENT_NOT_FOUND)`（传 8 位 BizCode）。

> ⚠️ 关于 `BizCode.SUCCESS`：枚举里**仍声明**它（`make_biz_code(SERVICE_CODE, BizCategory.SUCCESS, 0)`，8 位真值，如 `12000000`），但**不要传给 `success()`**。它存在的意义是：① 让"成功"在编码体系里有正式位置；② 供 `parse_biz_code` 解析/排障时标识。成功响应 envelope 里的 `biz_code` 一律是 `0`，不是 `BizCode.SUCCESS` 的 8 位值。
>
> 一句话：**成功 = `0`，错误 = 8 位 BizCode（异常透传）。`success()` 别传 biz_code。**

### 13.7 dataclass / DTO 中的 biz_code

biz_code 出现在统一响应的外层（`BaseResponse.biz_code`），**不进入** DTO / Entity / ORM Model。它是传输层语义，不是领域语义。

---

## 14. 记忆强化

> 🔒 **开始开发微服务时，立即回忆：**
>
> 1. **四类数据载体**：DTO（api）/ Entity·VO（domain）/ ORM Model（仅 infra）/ Client Schema（clients）——跨边界禁裸 dict。
> 2. **单向依赖**：api → application → domain ← infrastructure；clients 被 application 用。
> 3. **抽象在 domain，实现在 infrastructure**；接口在 clients/interface，实现按模式切换。
> 4. **一文件一职责**，扩展靠新增文件 + DI 注册。
> 5. **数据流**：API(DTO) → Command/Query → Domain(Entity) → Repository(_to_model) → Infrastructure(Model)，反向 _to_entity 回到 Entity 再转 DTO 出。
> 6. **应用层职责三分（§5.2）**：只读→`queries/`（可绕过聚合投影读模型）；单聚合写→`commands/`（逻辑直接写 execute）；跨聚合/多步流程/多用例复用→`services/`（应用服务编排，command 委托）；纯领域规则无 IO→`domain/` 领域服务。按决策树定位，不靠"主力/备胎"。
> 7. **业务码（§13）**：每个服务在 `foundation/biz_code.py` 定义 `SERVICE_CODE` + `BizCode(IntEnum)` 枚举（中文注释描述具体问题）；所有异常绑定 BizCode；`services_common` 只提供编码规则不含服务枚举表；新服务通过 `generate-service` 脚本分配服务码并检测冲突。

---

## 附录 A：端到端完整示例（一个 `User` 资源从 0 到 1）

> 本附录用**同一个 `User` 资源**贯穿所有层，展示"新增一个带读写的资源"时**每个文件长什么样、放哪里、怎么串起来**。照抄此结构即可保证零差异。涉及包名以 `account_service` 为例。

### A.1 需求

实现两个端点：
- `POST /api/v1/account/users`：创建用户（写 → Command）
- `GET  /api/v1/account/users/{user_id}`：查询用户详情（读 → Query）

涉及落库、查询、一个外部服务调用（上传头像到 asset-service）。

### A.2 文件清单（新增/修改）

```
app/domain/value_objects/email.py                         [新增] 值对象
app/domain/entities/user.py                               [新增] 实体（聚合根）
app/domain/repositories/user_repository.py                [新增] 仓储接口
app/domain/common/exceptions.py                           [改]   领域异常（绑定 BizCode）
foundation/biz_code.py                                    [新增] 服务业务码定义（SERVICE_CODE + BizCode 枚举）
app/infrastructure/persistence/models/user_model.py       [新增] ORM 模型（类名 ACCUserModel，表名 acc_user）
app/infrastructure/persistence/repositories/sql_user_repository.py  [新增] 仓储实现
app/infrastructure/modules.py                             [改]   绑定接口→实现
app/application/commands/create_user.py                   [新增] 写用例
app/application/queries/get_user_detail.py                [新增] 读用例
app/application/services/user_service.py                  [不建] 本例 create/get 均为单聚合，无需 service（跨聚合场景见 §5.2.4）
app/application/common/exception.py                       [改]   应用异常
app/application/modules.py                                [改]   注册 command/query（本例无 service 故不注册 service）
app/api/v1/schemas/user.py                                [新增] 请求/响应 DTO
app/api/v1/endpoints/user.py                              [新增] 端点
app/api/v1/router.py                                      [改]   挂载路由
foundation/config.py                                      [改]   外部服务地址
```

### A.3 Domain 层

```python
# app/domain/value_objects/email.py
import re
from {pkg}.app.domain.common.exceptions import InvariantViolation

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Email:
    """Email 值对象（不可变，构造即校验）"""

    def __init__(self, value: str):
        if not _EMAIL_RE.match(value or ""):
            raise InvariantViolation(f"非法邮箱: {value}")
        self._value = value

    @property
    def value(self) -> str:
        return self._value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Email) and other._value == self._value

    def __hash__(self) -> int:
        return hash(self._value)

    def __str__(self) -> str:
        return self._value
```

```python
# app/domain/entities/user.py
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

from services_common.utils.id import generate_id


class User(BaseModel):
    """User 聚合根"""
    user_id: str = Field(..., description="业务ID")
    username: str = Field(..., description="用户名")
    email: Optional[str] = Field(None, description="邮箱")
    is_active: bool = Field(default=True, description="是否启用")
    created_at: datetime = Field(default_factory=datetime.now)

    class Config:
        from_attributes = True

    # —— 领域行为：业务规则写在实体里，而不是散落在 service ——
    @classmethod
    def create(cls, username: str, email: Optional[str] = None) -> "User":
        return cls(user_id=generate_id(), username=username, email=email)

    def disable(self) -> None:
        self.is_active = False

    def rename(self, username: str) -> None:
        if not username.strip():
            from {pkg}.app.domain.common.exceptions import InvariantViolation
            raise InvariantViolation("用户名不能为空")
        self.username = username
```

```python
# app/domain/repositories/user_repository.py
from abc import ABC, abstractmethod
from typing import Optional
from {pkg}.app.domain.entities.user import User


class UserRepository(ABC):
    """User 仓储接口（一个聚合一个接口，禁止混入其它聚合的查询）"""

    @abstractmethod
    async def get_by_id(self, user_id: str) -> Optional[User]: ...

    @abstractmethod
    async def create(self, user: User) -> User: ...

    @abstractmethod
    async def update(self, user: User) -> User: ...

    @abstractmethod
    async def delete(self, user_id: str) -> None: ...
```

```python
# app/domain/common/exceptions.py  （领域异常，从 services_common 继承，绑定 BizCode）
from services_common.exceptions import BaseDomainException
from {pkg}.foundation.biz_code import BizCode


class InvariantViolation(BaseDomainException):
    """业务不变式违反 - 领域规则校验不通过"""

    def __init__(self, message: str):
        super().__init__(message, code="INVARIANT_VIOLATION",
                         biz_code=BizCode.INVARIANT_VIOLATION)


class UserNotFoundException(BaseDomainException):
    """用户不存在 - 查询的用户在数据库中未找到"""

    def __init__(self, user_id: str | None = None):
        msg = f"user not found: {user_id}" if user_id else "user not found"
        super().__init__(msg, code="USER_NOT_FOUND",
                         biz_code=BizCode.USER_NOT_FOUND)
```

### A.4 Infrastructure 层

```python
# app/infrastructure/persistence/models/user_model.py
from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from services_common.database import BaseModel


class ACCUserModel(BaseModel):
    """User ORM 模型（一表一文件；类名带服务前缀 ACC，表名带 service_prefix）"""
    __tablename__ = "acc_user"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="自增ID")
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, comment="业务ID")
    username: Mapped[str] = mapped_column(String(64), nullable=False, comment="用户名")
    email: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="邮箱")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    # created_at / updated_at 由 BaseModel 统一提供，此处不重复声明（见 §5.4.1）
```

```python
# app/infrastructure/persistence/repositories/sql_user_repository.py
from typing import Optional
from sqlalchemy import select
from injector import inject

from services_common.database import DatabaseManager
from {pkg}.foundation.logging import get_logger
from {pkg}.app.domain.entities.user import User
from {pkg}.app.domain.repositories.user_repository import UserRepository
from {pkg}.app.infrastructure.persistence.models.user_model import ACCUserModel

logger = get_logger(__name__)


class SQLUserRepository(UserRepository):
    """UserRepository 的 SQL 实现"""

    @inject
    def __init__(self, dm: DatabaseManager):
        self.dm = dm

    # —— 两个转换方法是硬约束：Model 不得越界，必须转 Entity ——
    def _to_entity(self, model: ACCUserModel) -> User:
        return User(
            user_id=model.user_id,
            username=model.username,
            email=model.email,
            is_active=model.is_active,
            created_at=model.created_at,
        )

    def _to_model(self, entity: User) -> ACCUserModel:
        return ACCUserModel(
            user_id=entity.user_id,
            username=entity.username,
            email=entity.email,
            is_active=entity.is_active,
            created_at=entity.created_at,
        )

    async def get_by_id(self, user_id: str) -> Optional[User]:
        async with self.dm.session() as session:
            result = await session.execute(
                select(ACCUserModel).where(ACCUserModel.user_id == user_id)
            )
            model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def create(self, user: User) -> User:
        async with self.dm.session() as session:
            model = self._to_model(user)
            session.add(model)
            await session.flush()
        return user

    async def update(self, user: User) -> User:
        async with self.dm.session() as session:
            result = await session.execute(
                select(ACCUserModel).where(ACCUserModel.user_id == user.user_id)
            )
            model = result.scalar_one()
            model.username = user.username
            model.email = user.email
            model.is_active = user.is_active
            await session.flush()
        return user

    async def delete(self, user_id: str) -> None:
        async with self.dm.session() as session:
            result = await session.execute(
                select(ACCUserModel).where(ACCUserModel.user_id == user_id)
            )
            model = result.scalar_one()
            await session.delete(model)
            await session.flush()
```

```python
# app/infrastructure/modules.py
from injector import Module, Binder


class InfrastructureModule(Module):
    def configure(self, binder: Binder):
        from {pkg}.app.domain.repositories.user_repository import UserRepository
        from {pkg}.app.infrastructure.persistence.repositories.sql_user_repository import SQLUserRepository
        binder.bind(UserRepository, to=SQLUserRepository, scope=None)
```

### A.5 Application 层

> 本节是完整可抄模板。本例的 `create`/`get` 都是**单聚合**用例，按 §5.2 决策树归 `commands/`/`queries/`，因此本例不含 service。**这不代表 service 是备选**——跨聚合/多步流程场景下 service 是第一类归属，见 A.5.1 与 §5.2.4。

```python
# app/application/commands/create_user.py  （写用例：直接注入仓储/clients，逻辑写在 execute）
from dataclasses import dataclass
from typing import Optional
from injector import inject

from {pkg}.app.domain.entities.user import User
from {pkg}.app.domain.repositories.user_repository import UserRepository
from {pkg}.clients.asset_service.interface import AssetService
from {pkg}.foundation.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CreateUserResult:
    user: User


class CreateUserCommand:
    @inject
    def __init__(self, user_repo: UserRepository, asset: AssetService):
        self.user_repo = user_repo              # ✅ 直接注入 domain 仓储接口
        self.asset = asset                      # ✅ 外部服务通过 clients 接口注入

    async def execute(
        self,
        username: str,
        email: Optional[str] = None,
        avatar: Optional[bytes] = None,
    ) -> CreateUserResult:
        logger.info("创建用户", operation="account.user.create", username=username)
        user = User.create(username=username, email=email)   # ✅ 领域工厂，逻辑在 command 内
        saved = await self.user_repo.create(user)

        if avatar:
            # clients 返回的是 Pydantic schema，不是裸 dict
            uploaded = await self.asset.upload_avatar(
                file_data=avatar, filename=f"{saved.user_id}.png", content_type="image/png",
            )
            logger.info("头像已上传", operation="account.user.create.avatar",
                        user_id=saved.user_id, asset_id=uploaded.asset_id)

        logger.info("创建用户成功", operation="account.user.create.success", user_id=saved.user_id)
        return CreateUserResult(user=saved)
```

```python
# app/application/queries/get_user_detail.py  （读用例：直接注入仓储）
from dataclasses import dataclass
from typing import Optional
from injector import inject

from {pkg}.app.domain.entities.user import User
from {pkg}.app.domain.repositories.user_repository import UserRepository
from {pkg}.foundation.logging import get_logger

logger = get_logger(__name__)


@dataclass
class GetUserDetailResult:
    user: User


class GetUserDetailQuery:
    @inject
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo              # ✅ query 也直接注入仓储，不经 service

    async def execute(self, user_id: str) -> Optional[GetUserDetailResult]:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            logger.info("用户不存在", operation="account.user.detail.not_found", user_id=user_id)
            return None
        return GetUserDetailResult(user=user)
```

```python
# app/application/modules.py
# 默认只注册 command/query；没有 service 就不要注册 service
from injector import Module, Binder


class ApplicationModule(Module):
    def configure(self, binder: Binder):
        from {pkg}.app.application.commands.create_user import CreateUserCommand
        binder.bind(CreateUserCommand, to=CreateUserCommand, scope=None)

        from {pkg}.app.application.queries.get_user_detail import GetUserDetailQuery
        binder.bind(GetUserDetailQuery, to=GetUserDetailQuery, scope=None)
```

#### A.5.1 何时归 `services/`（跨聚合/复用场景，附反例对照）

当用例**跨多个聚合事务**、或**多个 command/query 复用同一领域流程**时，application service 就是它的正当归属。例如「创建用户」和「批量导入用户」都需要"校验配额 + 落库 + 发欢迎事件"这一整套：

```python
# app/application/services/user_provisioning_service.py  （跨聚合/复用流程的归属）
from injector import inject
from services_common.database import DatabaseManager

from {pkg}.app.domain.entities.user import User
from {pkg}.app.domain.repositories.user_repository import UserRepository
from {pkg}.app.domain.repositories.quota_repository import QuotaRepository


class UserProvisioningService:
    """被 CreateUserCommand 和 ImportUsersCommand 共同复用的开通流程"""

    @inject
    def __init__(self, dm: DatabaseManager, user_repo: UserRepository, quota_repo: QuotaRepository):
        self.dm = dm
        self.user_repo = user_repo
        self.quota_repo = quota_repo

    async def provision(self, username: str, email: str | None) -> User:
        async with self.dm.transaction():               # ← service 的正当理由：跨聚合事务
            await self.quota_repo.consume(scope="user", amount=1)
            return await self.user_repo.create(User.create(username=username, email=email))
```

此时 command 才注入这个 service：

```python
class CreateUserCommand:
    @inject
    def __init__(self, provisioning: UserProvisioningService):
        self.provisioning = provisioning            # ✅ 复用成立 → 注入 service 合理
    async def execute(self, username: str, email: str | None = None) -> CreateUserResult:
        return CreateUserResult(user=await self.provisioning.provision(username, email))
```

> 判定（对应 §5.2 决策树）：**单聚合写**→留在 command；**跨聚合/多步流程/多用例复用**→application service；**纯领域规则无 IO**→domain service。service 是"跨聚合编排/可复用流程"的第一类归属，不是"每个域都要有"也不是"能不建就不建"。
```

### A.6 API 层

```python
# app/api/v1/schemas/user.py  （一资源一文件，可含多个 DTO 类）
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    email: Optional[str] = Field(None, max_length=128)


class UserResponse(BaseModel):
    user_id: str
    username: str
    email: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None

    @classmethod
    def from_entity(cls, user) -> "UserResponse":
        """Entity → DTO 的统一出口"""
        return cls(
            user_id=user.user_id,
            username=user.username,
            email=user.email,
            is_active=user.is_active,
            created_at=user.created_at,
        )
```

```python
# app/api/v1/endpoints/user.py
from fastapi import APIRouter, Depends, HTTPException, status

from services_common.response import success, DataResponse
from {pkg}.foundation.container import get_injector
from {pkg}.foundation.logging import get_logger
from {pkg}.app.application.commands.create_user import CreateUserCommand
from {pkg}.app.application.queries.get_user_detail import GetUserDetailQuery
from {pkg}.app.api.v1.schemas.user import CreateUserRequest, UserResponse

router = APIRouter(prefix="/users", tags=["users"])
logger = get_logger(__name__)


def _create_user_command() -> CreateUserCommand:
    return get_injector().get(CreateUserCommand)


def _get_user_detail_query() -> GetUserDetailQuery:
    return get_injector().get(GetUserDetailQuery)


@router.post("", response_model=DataResponse[UserResponse])
async def create_user(
    body: CreateUserRequest,
    command: CreateUserCommand = Depends(_create_user_command),
) -> DataResponse[UserResponse]:
    try:
        result = await command.execute(username=body.username, email=body.email)
        return success(data=UserResponse.from_entity(result.user))
    except Exception as e:
        logger.error("创建用户失败", operation="account.user.create.error", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="创建用户失败")


@router.get("/{user_id}", response_model=DataResponse[UserResponse])
async def get_user(
    user_id: str,
    query: GetUserDetailQuery = Depends(_get_user_detail_query),
) -> DataResponse[UserResponse]:
    result = await query.execute(user_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return success(data=UserResponse.from_entity(result.user))
```

```python
# app/api/v1/router.py
from fastapi import APIRouter
from {pkg}.app.api.v1.endpoints import user

api_router = APIRouter(prefix="/v1/account")
api_router.include_router(user.router)
```

### A.7 一次请求的完整数据流转

```
POST /api/v1/account/users  {"username": "alice", "email": "a@b.com"}
   │
   ▼  CreateUserRequest(DTO)                       ← api 校验
endpoints/user.create_user
   │  command.execute(username, email)
   ▼
commands/create_user.CreateUserCommand
   │  user_service.create(...)
   ▼
services/user_service.UserService
   │  User.create(...)                             ← domain 工厂，生成 Entity
   │  user_repo.create(user)                       ← 依赖接口（抽象）
   ▼
infrastructure/sql_user_repository.SQLUserRepository
   │  _to_model(user) → ACCUserModel → session.add    ← Entity → Model 落库
   ▼
返回 User(Entity) ──► CreateUserResult ──► UserResponse.from_entity ──► success(DataResponse[UserResponse])
```

---

## 附录 B：易错对照速查（❌ → ✅）

| 场景 | ❌ 错误 | ✅ 正确 |
|---|---|---|
| 端点返回 | `return {"user_id": uid}` | `return success(data=UserResponse.from_entity(user))` |
| 端点缺类型 | `@router.get("/x")` 无 `response_model` | `@router.get("/x", response_model=DataResponse[XxxResponse])` |
| repo 返回 | `return model`（ORM） | `return self._to_entity(model)` |
| application 依赖 | `from ...infrastructure...sql_user_repository import SQLUserRepository` | `from ...domain.repositories.user_repository import UserRepository`（注入接口） |
| clients 返回 | `return resp.json()` / `return {...}` | `return UserInfo(**resp.json().get("data", {}))` |
| clients import | `from {pkg}.clients.x import XProxy`（靠 `__init__`） | `from {pkg}.clients.x.api_proxy import XProxy`（完整路径） |
| 端点调外部 | 端点内 `httpx.get(...)` | 经 `clients` 接口注入后调用 |
| 多 Repo 同文件 | `repositories.py` 里写 `UserRepo` + `OrderRepo` | 拆 `user_repository.py` / `order_repository.py` |
| domain 依赖 | domain 里 `import sqlalchemy` / DTO | domain 只用 pydantic + 自身类型 |
| 表名 | `__tablename__ = "user"` | `__tablename__ = "acc_user"`（带 service_prefix） |
| Model 类名 | `class UserModel` | `class ACCUserModel`（带服务前缀全大写，防 all-in-one 类名冲突） |
| 同步 DB | `session.query(...).all()` | `await session.execute(select(...))` |
| 新增依赖 | 写完类忘记注册 | 同步在对应 `modules.py` `binder.bind(...)` |
| 业务逻辑位置 | 写在 endpoint 里 | 下沉到 command/query/service + 实体方法 |
| 单聚合写归属 | 抽 `XxxService` 让 command 空壳转调 | 逻辑直接写在 `commands/` 的 `execute` |
| 跨聚合写归属 | 多聚合事务全堆进单个 command | 抽 application service 编排事务，command 委托调用 |
| 读用例 | 为只读也加载整张聚合图 | `queries/` 直接投影为读模型（可不返回完整聚合） |
| service 定位 | 当成"复用才勉强建"的备胎 | 跨聚合/多步流程的第一类归属（见 §5.2 决策树） |
| 领域规则归属 | 纯领域规则写进 application service | 放 `domain/` 领域服务（无 IO） |
| 异常缺 biz_code | `super().__init__(msg, code="X")` | `super().__init__(msg, code="X", biz_code=BizCode.X)` |
| BizCode 无注释 | `AUTH_ERROR = make_biz_code(...)` | `AUTH_ERROR = make_biz_code(...)  # 用户名或密码错误` |
| 手写业务码数字 | `AUTH_ERROR = 17002001` | `AUTH_ERROR = make_biz_code(SERVICE_CODE, BizCategory.AUTH, 1)` |

---

*本规范应在每次开发 `services/` 微服务时引用，并以"消除差异"为唯一验收标准。*
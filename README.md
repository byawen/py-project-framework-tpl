# 框架开发指南

本项目采用微服务架构，分为两大类组件：

- **services/** — 对外提供 API/端口的微服务（FastAPI + uvicorn）
- **workers/** — 无 API/端口的后台任务进程（Celery 等消息消费者）

每一类都支持两种运行模式：

| 类别 | 独立模式 | 聚合模式                                             |
|------|----------|--------------------------------------------------|
| 服务 services | **Standalone** 每个服务独立运行 | **All-in-One** 所有服务组合成一个 FastAPI 进程              |
| 工作者 workers | **Standalone** 每个 worker 独立运行 | **Worker-in-One** 所有 worker 聚合到一进程（每个任务队列消费是多进程） |

聚合模式共享同一套 DB/Redis 连接，方便本地开发调试；独立模式适合按需部署与扩缩容。

---

## 扩展说明
目前 services/ 和 workers/ 在同一个仓库中，后续有多仓库时再拆分

## 快速开始

### 1. 安装 uv (包管理器)

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
irm https://astral.sh/uv/install.ps1 | iex
```

### 2. 安装依赖

```bash
# 安装所有服务依赖
make install

# 或仅安装某个服务依赖
make install-service SERVICE=pingpong-service
```

### 3. 启动服务

```bash
# All-in-One 模式 (推荐开发使用)
make all-in-one

# Standalone 模式 (独立服务)
make dev SERVICE=pingpong-service

# Docker Compose 启动基础设施 (数据库、Redis 等)
make compose-up
```

服务启动后访问：
- API 文档: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### 4. 启动 Worker (后台任务)

```bash
# Worker-in-One 模式 (所有 worker 聚合到一个进程)
make worker-in-one

# Standalone 模式 (单个 worker 独立运行)
cd workers/pingpong-worker && uv run python -m pingpong_worker.main
```

> Worker 没有 HTTP 端口，启动后通过消息中间件 (Redis/Celery) 消费任务，无 `/docs` 入口。

---

## 常用命令

### 基础命令

| 命令 | 说明 |
|------|------|
| `make help` | 查看所有可用命令 |
| `make install` | 安装所有服务依赖 |
| `make clean` | 清理缓存文件 |

### 服务管理

| 命令 | 说明 |
|------|------|
| `make dev SERVICE=<name>` | 启动开发服务器 (热重载) |
| `make install-service SERVICE=<name>` | 安装服务依赖 |
| `make lint-service SERVICE=<name>` | 代码检查 |
| `make test-service SERVICE=<name>` | 运行测试 |
| `make migrate-service SERVICE=<name>` | 运行数据库迁移 |
| `make migration-create SERVICE=<name> NAME=<migration_name>` | 创建数据库迁移 |
| `make docker-build-service SERVICE=<name>` | 构建 Docker 镜像 |

### 工作区管理

| 命令 | 说明 |
|------|------|
| `make add-service SERVICE=<name>` | 添加服务到工作区 |
| `make remove-service SERVICE=<name>` | 从工作区移除服务 |

### All-in-One 模式

| 命令 | 说明 |
|------|------|
| `make all-in-one` | 启动 All-in-One 开发模式 (热重载) |
| `make all-in-one-prod` | 启动 All-in-One 生产模式 |
| `make all-in-one-install` | 安装 All-in-One 依赖 |
| `make all-in-one-add` | 将 All-in-One 添加到工作区 |

### Worker (后台任务)

| 命令 | 说明 |
|------|------|
| `make worker-in-one` | 启动 Worker-in-One 模式 (所有 worker 聚合到一个进程) |
| `make worker-in-one-install` | 安装 Worker-in-One 依赖 |
| `make generate-worker WORKER=<name> SHORT_PREFIX=<prefix>` | 生成一个新 worker (无 API、无端口) |

### Docker Compose

| 命令 | 说明 |
|------|------|
| `make compose-up` | 启动所有基础设施服务 |
| `make compose-up-dev` | 启动开发环境基础设施 |
| `make compose-down` | 停止所有基础设施服务 |
| `make compose-logs` | 查看日志 |

### 其他命令

| 命令 | 说明 |
|------|------|
| `make lint` | 运行所有服务代码检查 |
| `make test` | 运行所有服务测试 |
| `make migrate` | 运行所有服务数据库迁移 |
| `make docker-build` | 构建所有服务 Docker 镜像 |
| `make health` | 检查所有服务健康状态 |
| `make docs` | 生成所有服务文档 |
| `make services` | 列出所有可用服务 |

---

## 目录结构

```
/
├── services/                     # 微服务源码 (API + 端口)
│   ├── common/                   # 公共服务库 (services-common)
│   │   └── src/
│   │       └── services_common/  # 服务共享模块 (含 FastAPI/Web 能力)
│   └── pingpong-service/         # 示例服务
│       └── src/
│           └── pingpong_service/ # 服务代码
├── all-in-one/                   # All-in-One 组合应用 (聚合所有 service)
│   └── src/
│       └── all_in_one/           # 入口模块
├── workers/                      # 后台任务源码 (无 API、无端口)
│   ├── common/                   # 公共 worker 库 (workers-common)
│   │   └── src/
│   │       └── workers_common/   # worker 共享模块 (无 Web 依赖)
│   └── pingpong-worker/          # 示例 worker
│       └── src/
│           └── pingpong_worker/  # worker 代码 (broker/handlers/...)
├── worker-in-one/                # Worker-in-One 组合进程 (聚合所有 worker)
│   └── src/
│       └── worker_in_one/        # 入口模块 (broker 聚合编排)
├── infrastructure/               # 基础设施配置
│   ├── docker-compose.yml        # Docker Compose 配置
│   └── kubernetes/               # K8s 配置
├── scripts/                      # 辅助脚本 (含 generate-service / generate-worker)
├── Makefile                      # 构建命令
└── README.md                     # 本文档
```

---

## 开发指南

### 模式 1: Standalone 独立服务模式

每个服务独立运行，有自己的依赖和配置。

```bash
# 启动单个服务
make dev SERVICE=pingpong-service

# 服务运行在独立端口 (如 8001)
# 访问 API 文档: http://localhost:8001/docs
```

---

### 模式 2: All-in-One 组合模式

所有服务组合成一个 FastAPI 应用，统一入口。

```bash
# 启动
make all-in-one

# 访问 http://localhost:8000/docs
```

---

### 模式 3: Worker Standalone 独立模式

每个 worker 独立运行，独立消费消息中间件中的任务。

```bash
cd workers/pingpong-worker && uv run python -m pingpong_worker.main
```

worker 在 `main.py` 中显式创建 broker 实例并注册到 `BrokerManager` (celery / rabbitmq / pubsub ...)，
broker 抽象位于 `workers/<worker>/src/<worker>/broker/`，新增中间件只需:

1. 在 `broker/implementations/` 下新建实现类，继承 `BaseBroker`
2. 在 `broker/factory.py` 的 `BROKER_REGISTRY` 中注册一行

---

### 模式 4: Worker-in-One 组合模式

所有 worker 聚合到同一个进程，共享 DB/Redis 连接。

```bash
make worker-in-one
```

聚合进程通过 **聚合 Broker 抽象** 支持多种中间件并存：

```
workers_registry()  ->  [WorkerSpec{name, broker_type, register_handlers}...]
                            │  broker_type 在 WorkerSpec 中显式指定
BrokerRunner.build()  ->  按 broker_type 分组，每组创建一个聚合 Broker
BrokerRunner.run()    ->  需要主线程的 Broker(如 Celery) 占前台
                          其余 Broker 进 daemon 线程并发运行
```

- 同类型中间件的多个 worker 共享同一个聚合 Broker 实例
- 不同类型中间件的 worker 在同一进程内并发消费，互不阻塞
- 扩展新中间件: 在 `worker-in-one/src/worker_in_one/broker/implementations/` 新建实现类继承 `AggregateBroker`，并在 `factory.py` 的 `AGGREGATE_BROKER_REGISTRY` 注册

---

### 添加新服务到工作区

1. **创建服务目录** (services/xxxx-service)
   ```bash
   make generate-service SERVICE=your-new-service SHORT_PREFIX=yns SERVICE_CODE=20 PORT=8001
   ```

   > `SERVICE_CODE`（1-89）是全局唯一的服务编号，用于生成 8 位业务码（biz_code）。
   > 脚本会自动检测服务码冲突（与 port、prefix 检测逻辑一致），并写入 `service.metadata`。

2. **添加服务到工作区**
   ```bash
   make add-service SERVICE=your-new-service
   ```

3. **安装依赖**
   ```bash
   make install-service SERVICE=your-new-service
   ```

4. **添加到 All-in-One** (可选)
   
   编辑 `all-in-one/src/all_in_one/config.py`:
   
5. ```python
    def get_xxx_settings(self) -> XxxxxxSettings:
        """获取 Xxxxx 服务配置"""
        # 从当前配置中提取 Xxxx 相关的配置
        return XxxxxSettings(
            APP_NAME=self.APP_NAME + "-xxxxx",
            DEBUG=self.DEBUG,
            ENVIRONMENT=self.ENVIRONMENT,
            HOST=self.HOST,
            PORT=self.PORT,
            CORS_ORIGINS=self.CORS_ORIGINS,
            DATABASE_URL=self.DATABASE_URL,
            DB_POOL_SIZE=self.DB_POOL_SIZE,
            DB_MAX_OVERFLOW=self.DB_MAX_OVERFLOW,
            DB_ECHO=self.DB_ECHO,
            REDIS_URL=self.REDIS_URL,
            REDIS_MAX_CONNECTIONS=self.REDIS_MAX_CONNECTIONS,
            REDIS_PREFIX="xxxx",
        )
   ```
   编辑 `all-in-one/src/all_in_one/services.py`:
   
   ```python
    try:
        from your_service.main import setup as your_setup
        service_settings = _settings._settings.get_xxx_settings()
        cleaner = await your_setup(app, service_settings, logger)
        cleaner_list.append(cleaner)
        _services_registry[service_settings.APP_NAME] = {"enabled": True}
    except Exception as e:
        logger.warning(f"Failed to load your-service: {e}")
   ```

---

### 添加新 Worker 到工作区

1. **生成 worker 目录** (workers/xxxx-worker)
   ```bash
   make generate-worker WORKER=your-new-worker SHORT_PREFIX=ynw
   ```
   > 脚本会基于 pingpong-worker 模板生成代码，替换名称与前缀，
   > 校验前缀是否与现有 service/worker 冲突，并更新根 `pyproject.toml`。

2. **安装依赖**
   ```bash
   make worker-in-one-install
   ```

3. **添加到 Worker-in-One** (可选)

   编辑 `worker-in-one/src/worker_in_one/config.py`，新增该 worker 的配置提取方法:

   ```python
    def get_xxx_worker_settings(self):
        config_dict = vars(self).copy()
        config_dict.update({
            "MODEL": "worker-in-one",
            "APP_NAME": self.APP_NAME + "-xxx",
            "REDIS_PREFIX": "xxx",
        })
        return XxxWorkerSettings(**config_dict)
   ```

   编辑 `worker-in-one/src/worker_in_one/workers.py`，在 `workers_registry` 中加载并产出 `WorkerSpec`:

   ```python
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
    except Exception as e:
        logger.warning(f"Failed to load xxx-worker: {e}")
   ```

---

### 热重载配置

All-in-One 模式支持热重载，修改以下目录中的代码会自动重启：

- `services/*` - 所有服务源码
- `all-in-one/src/*` - All-in-One 入口

Standalone 模式由各服务自己的配置决定 (通常使用 uvicorn `--reload`)

---

### 配置管理

#### All-in-One 配置

配置文件：`all-in-one/src/all_in_one/config.py`

主要配置项：

| 配置 | 说明 | 默认值 |
|------|------|--------|
| `DATABASE_URL` | PostgreSQL 连接地址 | postgresql+asyncpg://... |
| `REDIS_URL` | Redis 连接地址 | redis://localhost:6379/0 |
| `ENABLE_PINGPONG` | 启用 PingPong 服务 | true |
| `DEBUG` | 调试模式 | true |

#### Standalone 服务独立配置

各服务在 `services/<service>/.env` 中配置

---

## 架构说明

### 公共服务 (services-common)

`services-common` 提供所有 **service** 共享的基础能力：

| 模块 | 说明 |
|------|------|
| **DatabaseManager** | 数据库连接管理，支持事务和重试 |
| **RedisManager** | Redis 连接管理 |
| **HealthChecker** | 健康检查 |
| **配置继承** | 各服务可继承基础配置类 |
| **Web 能力** | HTTP response、中间件、异常处理器、uvicorn JSON 日志等 |

### 公共 Worker 库 (workers-common)

`workers-common` 提供所有 **worker** 共享的基础能力，**不依赖 FastAPI/uvicorn**：

| 模块 | 说明 |
|------|------|
| **DatabaseManager / BaseModel** | 数据库连接管理 (异步 SQLAlchemy) |
| **RedisManager / RedisWorkerLock** | Redis 连接管理 + 单活 worker 锁 |
| **配置继承** | 去掉 HOST/PORT/CORS 等 Web 字段的配置基类 |
| **SharedResources** | Worker-in-One 共享 DB/Redis 注册表 |
| **logging / exceptions / utils** | 统一日志、异常基类、工具函数 |

> **边界约束**: `workers/` 代码 **禁止** import `services_common`。
> services 与 workers 是两个独立领域边界，各自使用自己的 common 库，
> 避免后台任务进程被迫携带 Web 框架依赖。

### Worker 分层结构

worker 用 `handlers/` 取代 service 的 `api/`，用 `broker/` 抽象消息中间件：

```
broker/                 # 消息中间件抽象 (可插拔)
├── base.py             # BaseBroker 抽象接口
├── factory.py          # BROKER_REGISTRY 工厂
└── implementations/    # celery_broker.py 等具体实现
handlers/               # 任务入口层 (等价于 service 的 api 层)
├── registry.py         # 集中注册所有 handler 到 broker
└── xxx_demo.py         # 具体 handler
app/                    # DDD 分层 (domain / application / infrastructure)
```

### 领域驱动设计

```
domain/
├── entities/           # 领域实体
├── repositories/      # 仓储接口 (抽象)
└── value_objects/     # 值对象
...
infrastructure/
└── persistence/
    └── repositories/  # 仓储实现 (SQL)
```

### 统一业务码（biz_code）

所有 API 响应外层携带 `biz_code` 字段（8 位整数），用于跨服务精确定位业务场景：

```
biz_code = 1 SS DDD EEE
           │ │  │   └─ 3位 业务序号 (001-999, 0=成功)
           │ │  └──── 3位 业务大类 (认证/校验/未找到/冲突...)
           │ └──────── 2位 服务编号 (00-89, 00=模板/公共)
           └────────── 固定前缀 1（保证始终 8 位数）
```

- **服务编号** 全局唯一，由 `generate-service` 脚本分配，写入 `service.metadata` 的 `service_code` 字段
- **业务大类** 由 `services_common.biz_code.BizCategory` 统一定义，所有服务共用
- 各服务在 `foundation/biz_code.py` 中定义 `BizCode(IntEnum)` 枚举，每个成员带中文注释描述具体问题
- 所有异常绑定 BizCode，由异常处理器自动透传到响应

> 详细规范见 `develop/ai-coding-service-app.md` §13。

---

## 其他

### 查看可用服务列表

```bash
make services
# 或
make help
```

### 热重载不生效

确保使用 `make all-in-one` 命令启动，它包含了正确的 `--reload-dir` 参数。

### 连接数据库

修改对应配置文件中的 `DATABASE_URL`：
- All-in-One: `all-in-one/.env`
- Standalone 服务: `services/<service>/.env`
- Worker-in-One: `worker-in-one/.env`
- Standalone Worker: `workers/<worker>/.env`

### 生成新 worker

```bash
make generate-worker WORKER=content-ops SHORT_PREFIX=cops
```

### 为 worker 切换/新增消息中间件

worker 在 `main.py` 中显式创建 broker 实例并注册到 `BrokerManager` (默认 `celery`)。
新增中间件实现后，在对应注册表登记即可:
- 单 worker: `workers/<worker>/.../broker/factory.py` 的 `BROKER_REGISTRY`
- Worker-in-One: `worker-in-one/.../broker/factory.py` 的 `AGGREGATE_BROKER_REGISTRY`

### 只运行某个服务的测试

```bash
make test-service SERVICE=pingpong-service
```

### 创建数据库迁移

```bash
make migration-create SERVICE=pingpong-service NAME=add_new_field
```

### 查看所有健康状态

```bash
make health
```

---

## 环境要求

- Python 3.10+
- Docker & Docker Compose
- uv (包管理器)

---

## 许可证

MIT License

# 框架开发指南

本项目采用微服务架构，支持两种运行模式：

1. **Standalone 独立服务模式** - 每个服务独立运行
2. **All-in-One 模式** - 所有服务组合成一个应用，方便开发调试

---

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
├── services/                     # 微服务源码
│   ├── common/                   # 公共服务 (services-common)
│   │   └── src/
│   │       └── services_common/  # 共享模块
│   └── pingpong-service/         # 示例服务
│       └── src/
│           └── pingpong_service/ # 服务代码
├── all-in-one/                   # All-in-One 组合应用
│   └── src/
│       └── all_in_one/           # 入口模块
├── infrastructure/               # 基础设施配置
│   ├── docker-compose.yml        # Docker Compose 配置
│   └── kubernetes/               # K8s 配置
├── scripts/                      # 辅助脚本
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

**优点**：服务独立，易于调试和扩展
**缺点**：需要管理多个端口，依赖可能重复

---

### 模式 2: All-in-One 组合模式

所有服务组合成一个 FastAPI 应用，统一入口。

```bash
# 启动
make all-in-one

# 访问 http://localhost:8000/docs
```

**优点**：
- 单一入口，单一端口
- 共享依赖，减少资源占用
- 适合开发调试

**缺点**：
- 所有服务共享同一进程
- 一个服务崩溃可能影响其他服务

---

### 添加新服务到工作区

1. **创建服务目录** (services/xxxx-service)
   ```bash
   make generate-service SERVICE=your-new-service
   ```

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

`services-common` 提供所有服务共享的基础能力：

| 模块 | 说明 |
|------|------|
| **DatabaseManager** | 数据库连接管理，支持事务和重试 |
| **RedisManager** | Redis 连接管理 |
| **HealthChecker** | 健康检查 |
| **配置继承** | 各服务可继承基础配置类 |

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
- Standalone: `services/<service>/.env`

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

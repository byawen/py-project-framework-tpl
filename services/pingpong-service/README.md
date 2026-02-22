# PingPong Service

PingPong Service

## Overview

PingPong Service 是一个基于 **Domain-Driven Design (DDD)** 架构模式和 **CQRS** (Command Query Responsibility Segregation) 设计模式构建的 FastAPI 微服务。该服务展示了现代化的 Python 后端架构实践。

## Architecture

### 技术栈

- **Web Framework**: FastAPI 2.0+
- **Database**: PostgreSQL 15+ (async via SQLAlchemy 2.0 + asyncpg)
- **Cache**: Redis 7+
- **Dependency Injection**: Injector
- **Configuration**: Pydantic Settings

### 项目结构 (DDD + CQRS)

```
pingpong_service/
├── app/                          # 主应用代码
│   ├── api/                      # API Layer (表现层)
│   │   └── v1/
│   │       ├── endpoints/        # API 端点
│   │       ├── router.py         # 路由聚合
│   │       └── schemas/          # Pydantic 请求/响应模型
│   ├── application/              # Application Layer (应用层)
│   │   ├── commands/            # Command 处理器 (写操作)
│   │   ├── queries/             # Query 处理器 (读操作)
│   │   ├── services/            # 封装业务逻辑/集合实现
│   │   └── common/              # 应用层公共组件
│   ├── domain/                  # Domain Layer (领域层)
│   │   ├── entities/            # 领域实体 (Ping, Pong)
│   │   ├── repositories/        # 仓储接口
│   │   ├── value_objects/       # 值对象
│   │   ├── caches/              # 缓存接口
│   │   └── common/              # 领域公共组件
│   └── infrastructure/           # Infrastructure Layer (基础设施层)
│       ├── persistence/         # 数据库持久化实现
│       │   ├── models/          # SQLAlchemy ORM 模型
│       │   └── repositories/   # 仓储实现
│       ├── caches/              # Redis 缓存实现
│       └── security/            # 安全相关
├── foundation/                   # 基础
│   ├── config.py                # 配置管理
│   ├── container.py             # 依赖注入容器
│   ├── logging.py               # 日志管理
│   └── exception_handlers.py    # 全局异常处理
├── clients/                      # 外部服务客户端
│   └── github/                  # GitHub OAuth 客户端
└── pkg/                          # 公共工具包
    └── helper/                  # 辅助函数
```

### 核心设计模式

1. **DDD 分层架构**
   - **API Layer**: 处理 HTTP 请求/响应
   - **Application Layer**: 编排业务流程，协调领域对象
   - **Domain Layer**: 核心业务逻辑和规则
   - **Infrastructure Layer**: 外部依赖实现 (数据库、缓存、第三方服务)

2. **CQRS 模式**
   - **Command**: `PongCommand` - 处理写操作 (创建 Pong)
   - **Query**: `PingQuery` - 处理读操作 (获取 Ping)

3. **Repository 模式**
   - 抽象数据访问，定义仓储接口
   - 实现类: `SqlPingRepository`, `SqlPongRepository`

## Quick Start

### 前置要求

- Python 3.12+
- PostgreSQL 15+
- Redis 7+

### 安装

```bash
# 安装依赖
cd services/pingpong-service
pip install -e ".[dev]"

# 或使用 uv
uv sync
```

### 配置

创建 `.env` 文件：

```bash
# App
APP_NAME=pingpong-service
DEBUG=true
ENVIRONMENT=development

# Server
HOST=0.0.0.0
PORT=8001

# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/pingpongs

# Redis
REDIS_URL=redis://localhost:6379/0

# External Services
GITHUB_SERVICE_URL=http://localhost:8003
```

### 运行

```bash
# 开发模式
uvicorn pingpong_service.main:app --reload --port 8001

# 或使用 Makefile
make run SERVICE=pingpong-service
```

### API 文档

启动服务后访问：

- **Swagger UI**: http://localhost:8001/docs
- **ReDoc**: http://localhost:8001/redoc

## API Endpoints

### Ping

```http
GET /api/v1/pingpong/ping
```

**Response:**
```json
{
  "message": "ping, xxxxxx",
  "ping_id": "uuid-string",
  "created_at": "2024-01-01T00:00:00Z"
}
```

### Pong

```http
POST /api/v1/pingpong/pong
Content-Type: application/json

{
  "data": "your-data-here"
}
```

**Response:**
```json
{
  "data": "your-data-here",
  "pong_id": "uuid-string",
  "created_at": "2024-01-01T00:00:00Z"
}
```

### Health Check

```http
GET /health
```

## Development

### 代码规范

```bash
# Lint
make lint SERVICE=pingpong-service

# Type Check
make type-check SERVICE=pingpong-service
```

### 测试

```bash
# 运行测试
pytest

# 带覆盖率
pytest --cov=pingpong_service
```

## Project Dependencies

### 主要依赖

- **fastapi**: 现代高性能 Web 框架
- **sqlalchemy**: SQL 工具包和 ORM
- **asyncpg**: PostgreSQL 异步驱动
- **redis**: Redis 异步客户端
- **injector**: 依赖注入框架
- **pydantic**: 数据验证和设置管理
- **services-common**: 内部共享库

## License

MIT License

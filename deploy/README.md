# ZeroOne Project - All-in-One 部署指南

本目录包含 All-in-One 架构的部署脚本和配置文件。

## 目录结构

```
deploy/
├── config/
│   ├── all-in-one.env.example         # All-in-One 环境配置示例
│   └── worker-in-one.env.example      # Worker-in-One 环境配置示例
├── scripts/
│   ├── deploy.sh                      # 主部署脚本
│   ├── deploy-all-in-one.sh           # All-in-One 快捷部署脚本
│   └── deploy-worker-in-one.sh        # Worker-in-One 快捷部署脚本
├── Dockerfile.all-in-one              # All-in-One Docker 镜像
├── Dockerfile.worker-in-one           # Worker-in-One Docker 镜像
├── local/
│   └── docker-compose.yml             # 本地 Docker Compose 相关
└── README.md                          # 本文件
```

## 快速开始

### 1. 准备环境配置

复制环境配置示例文件并根据实际情况修改：

```bash
cd deploy
cp config/all-in-one.env.example config/all-in-one.env
```

编辑 `config/all-in-one.env`，配置必要的参数：
- 数据库连接信息
- Redis 连接信息
- 各服务的 API 密钥

**注意**：
- Docker Compose 方式会通过 `env_file` 自动加载 `config/all-in-one.env`
- 直接运行容器时，镜像内已包含默认的 `.env` 文件（从 `all-in-one/env.example` 复制）
- 生产环境建议通过 `--env-file` 或 `-e` 参数覆盖配置

### 2. 使用部署脚本

如果你已经有独立的数据库和 Redis 服务，可以使用部署脚本：

```bash

deploy/scripts/deploy-all-in-one.sh

or 

cd deploy/scripts

# 部署 All-in-One 服务
./deploy-all-in-one.sh deploy

# 查看服务状态
./deploy-all-in-one.sh status

# 停止服务
./deploy-all-in-one.sh stop
```

或者直接使用主脚本：

```bash
cd deploy/scripts

# 部署
SERVICES="all-in-one" ./deploy.sh deploy

# 查看状态
SERVICES="all-in-one" ./deploy.sh status

# 停止
SERVICES="all-in-one" ./deploy.sh stop
```

**注意**：使用部署脚本时，需要确保 `deploy/config/all-in-one.env` 文件存在并已正确配置。脚本会通过 `--env-file` 参数将配置传递给容器。

### 3. 部署 Worker-in-One

Worker-in-One 将所有 Celery Worker（pingpong-worker / content-ops-worker 等）聚合在单一进程中运行。

```bash
cd deploy
cp config/worker-in-one.env.example config/worker-in-one.env
# 编辑 worker-in-one.env，配置 LLM API Key、回调地址等
```

```bash
cd deploy/scripts

# 部署 Worker-in-One
./deploy-worker-in-one.sh deploy

# 查看服务状态
./deploy-worker-in-one.sh status

# 停止服务
./deploy-worker-in-one.sh stop
```

或者直接使用主脚本：

```bash
cd deploy/scripts

# 部署
SERVICES="worker-in-one" ./deploy.sh deploy

# 查看状态
SERVICES="worker-in-one" ./deploy.sh status

# 停止
SERVICES="worker-in-one" ./deploy.sh stop
```

### 同时部署 All-in-One 和 Worker-in-One

```bash
cd deploy/scripts
SERVICES="all-in-one worker-in-one" ./deploy.sh deploy
```

## 环境变量说明

### 核心配置

- `APP_NAME`: 应用名称
- `DEBUG`: 调试模式（生产环境设为 false）
- `ENVIRONMENT`: 运行环境（development/production）
- `LOG_LEVEL`: 日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL）

### 数据库配置

- `DATABASE_URL`: PostgreSQL 连接字符串
- `DB_POOL_SIZE`: 数据库连接池大小
- `DB_MAX_OVERFLOW`: 连接池最大溢出数

### Redis 配置

- `REDIS_URL`: Redis 连接字符串
- `REDIS_MAX_CONNECTIONS`: Redis 最大连接数

### 服务配置

各服务使用前缀区分配置：
- `ACC_*`: Account 服务配置
- `ANA_*`: Analytics 服务配置
....

详细配置说明请参考 `config/all-in-one.env.example`。

## 自定义配置

### 修改端口

默认端口为 8000，可以通过环境变量修改：

```bash
# 使用部署脚本
ALL_IN_ONE_HTTP_PORT=9000 ./deploy-all-in-one.sh deploy

# 使用 docker-compose
# 修改 docker-compose.yml 中的 ports 配置
```

### 修改数据存储路径

默认数据存储在 `/opt/deploy-service/all-in-one`，可以通过环境变量修改：

```bash
REMOTE_APP_DIR=/data ./deploy-all-in-one.sh deploy
```

### 自定义镜像标签

```bash
TAG=v1.0.0 ./deploy-all-in-one.sh deploy
```

## 健康检查

部署完成后，可以通过以下方式检查服务状态：

```bash
# 健康检查端点
curl http://localhost:8000/health

# API 文档
open http://localhost:8000/docs
```

## 数据库迁移

首次部署或更新后，需要运行数据库迁移：

```bash
# service 数据库迁移
./migrate-service.sh
# worker 数据库迁移
./migrate-worker.sh
```
或者
```bash
# 进入容器
docker exec -it all-in-one bash

# 运行迁移（根据实际服务调整）
cd /workspace/services/pingpong-service
alembic upgrade head

# ... 其他服务


```

## 日志查看

```bash
# Docker Compose 方式
docker-compose logs -f all-in-one

# 部署脚本方式
docker logs -f deploy-claw-all-in-one
```

## 故障排查

### 服务无法启动

1. 检查环境配置文件是否正确
2. 检查数据库和 Redis 是否可访问
3. 查看容器日志：`docker logs deploy-all-in-one`

### 数据库连接失败

1. 确认 `DATABASE_URL` 配置正确
2. 确认数据库服务已启动
3. 检查网络连接

### Redis 连接失败

1. 确认 `REDIS_URL` 配置正确
2. 确认 Redis 服务已启动
3. 检查网络连接

## 生产环境建议

1. **修改所有默认密钥**：JWT_SECRET_KEY、数据库密码等
2. **启用 HTTPS**：使用 Nginx 反向代理并配置 SSL 证书
3. **配置日志收集**：使用 ELK、Loki 等日志系统
4. **配置监控告警**：使用 Prometheus + Grafana
5. **定期备份数据库**：设置自动备份策略
6. **限制 CORS 来源**：不要使用 `*`，指定具体域名
7. **使用专用用户运行**：不要使用 root 用户

## 更新部署

```bash
# 1. 拉取最新代码
git pull

# 2. 重新构建并部署
cd deploy/scripts
./deploy-all-in-one.sh deploy

# 3. 运行数据库迁移（如有需要）
docker exec -it deploy-all-in-one bash
# 在容器内运行迁移命令
```

## 回滚

如果新版本有问题，可以回滚到之前的镜像：

```bash
# 查看可用镜像
docker images | grep deploy-all-in-one

# 停止当前服务
docker rm -f deploy-all-in-one

# 使用旧版本镜像启动
docker run -d \
  --name deploy-all-in-one \
  --network zeroone-net \
  --env-file config/all-in-one.env \
  -v /opt/zeroone/all-in-one/uploads:/workspace/uploads \
  -v /opt/zeroone/all-in-one/data:/workspace/data \
  -p 8000:8000 \
  --restart unless-stopped \
  deploy-all-in-one:旧版本TAG
```

## 技术支持

如有问题，请联系开发团队或提交 Issue。
# 配置文件说明

本目录包含 All-in-One 部署的环境配置文件。

## 配置文件使用方式

### 1. Docker Compose 部署

Docker Compose 会自动加载 `all-in-one.env` 文件：

```yaml
# docker-compose.yml
all-in-one:
  env_file:
    - ./config/all-in-one.env  # 自动加载此文件
```

使用步骤：
```bash
cd deploy
cp config/all-in-one.env.example config/all-in-one.env
# 编辑 all-in-one.env
docker-compose up -d
```

### 2. 部署脚本方式

部署脚本通过 `--env-file` 参数传递配置：

```bash
cd deploy/scripts
./deploy-all-in-one.sh deploy
```

脚本会自动使用 `deploy/config/all-in-one.env` 文件。

### 3. 直接运行容器

如果直接使用 `docker run`，可以通过以下方式提供配置：

```bash
# 方式 1: 使用 --env-file
docker run -d \
  --name deploy-all-in-one \
  --env-file /path/to/all-in-one.env \
  -p 8000:8000 \
  deploy-all-in-one:latest

# 方式 2: 使用 -e 逐个指定
docker run -d \
  --name deploy-all-in-one \
  -e DATABASE_URL=postgresql+asyncpg://... \
  -e REDIS_URL=redis://... \
  -p 8000:8000 \
  deploy-all-in-one:latest

# 方式 3: 使用镜像内置的默认配置（不推荐生产环境）
docker run -d \
  --name deploy-all-in-one \
  -p 8000:8000 \
  deploy-all-in-one:latest
```

## 配置文件结构

```
config/
├── all-in-one.env.example    # 配置模板（包含所有配置项说明）
└── all-in-one.env            # 实际使用的配置（需要自己创建，不提交到 Git）
```

## 重要提示

1. **不要提交 `all-in-one.env` 到 Git**
   - 此文件包含敏感信息（密钥、密码等）
   - 已在 `.gitignore` 中排除

2. **生产环境必须修改的配置**
   - `DATABASE_URL`: 数据库连接字符串
   - `REDIS_URL`: Redis 连接字符串
   - 各服务的 API 密钥

3. **配置优先级**
   - 环境变量 > .env 文件 > 默认值
   - Docker 的 `-e` 参数会覆盖 `--env-file` 中的同名变量

4. **镜像内置配置**
   - Dockerfile 会将 `all-in-one/env.example` 复制为容器内的 `.env`
   - 这是为了确保容器能够启动（即使没有外部配置）
   - 生产环境应该通过外部配置覆盖默认值

## 配置验证

部署后可以通过以下方式验证配置是否生效：

```bash
# 查看容器环境变量
docker exec deploy-all-in-one env | grep -E "DATABASE_URL|REDIS_URL|LOG_LEVEL"

# 查看应用日志
docker logs deploy-all-in-one

# 健康检查
curl http://localhost:8000/health
```

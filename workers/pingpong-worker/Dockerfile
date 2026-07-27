# pingpong Worker 镜像
# 独立运行 pingpong-worker（Celery worker + beat），无 HTTP 端口
#
# 构建上下文必须为仓库根目录：
#   docker build -t pingpong-worker:latest -f workers/pingpong-worker/Dockerfile .
ARG PYTHON_BASE_IMAGE=python:3.12-slim
FROM ${PYTHON_BASE_IMAGE}

# 环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Shanghai

# 系统依赖：
#   build-essential / libpq-dev — asyncpg、bcrypt 编译所需
#   curl     — 容器内排障
#   tzdata   — 时区
RUN sed -i 's/deb.debian.org/mirrors.tencent.com/g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
        tzdata && \
    ln -snf /usr/share/zoneinfo/${TZ} /etc/localtime && \
    echo ${TZ} > /etc/timezone && \
    rm -rf /var/lib/apt/lists/*

# uv（快速 Python 包管理器）
RUN pip install --no-cache-dir uv \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn

WORKDIR /workspace

# 复制 worker 依赖源码（pingpong-worker 依赖 workers-common，均为 workspace 成员）
COPY workers/common /workspace/workers/common
COPY workers/pingpong-worker /workspace/workers/pingpong-worker

# 按依赖顺序安装：先 workers-common，再 pingpong-worker
RUN uv pip install --system -e ./workers/common \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn
RUN uv pip install --system -e ./workers/pingpong-worker \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn

# 日志目录
RUN mkdir -p /workspace/workers/pingpong-worker/logs

# 非 root 用户
RUN adduser --disabled-password --gecos '' appuser && \
    chown -R appuser:appuser /workspace
USER appuser

# 切换到 worker 工作目录（便于运行 alembic 等本地命令）
WORKDIR /workspace/workers/pingpong-worker

# 健康检查：worker 无 HTTP 端口，检测进程是否存活
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD pgrep -f "pingpong_worker" > /dev/null || exit 1

# 启动 worker（main.py 内部注册 handler、注入 beat schedule 并启动 Celery）
CMD ["python", "-m", "pingpong_worker.main"]
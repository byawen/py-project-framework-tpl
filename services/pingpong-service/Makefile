# ============================================================
# Service - 本地开发命令
# ============================================================

# 颜色定义
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[1;33m
BLUE := \033[0;34m
NC := \033[0m # No Color

# Alembic 配置
ALEMBIC_CONFIG := -c alembic.ini
ALEMBIC := alembic $(ALEMBIC_CONFIG)

# 帮助信息
.PHONY: help
help:
	@echo ""
	@echo "$(BLUE)╔═══════════════════════════════════════════════════════════════╗$(NC)"
	@echo "$(BLUE)║                   Service - Development Commands              ║$(NC)"
	@echo "$(BLUE)╚═══════════════════════════════════════════════════════════════╝$(NC)"
	@echo ""
	@echo "$(GREEN)Usage:$(NC)"
	@echo "  make $(YELLOW)<target>$(NC) [ARGS='...']"
	@echo ""
	@echo "$(GREEN)Main Targets:$(NC)"
	@echo "  $(YELLOW)install$(NC)             Install dependencies"
	@echo "  $(YELLOW)migrate$(NC)            Run all pending migrations"
	@echo "  $(YELLOW)migrate-up$(NC)         Upgrade to latest migration"
	@echo "  $(YELLOW)migrate-down$(NC)       Downgrade last migration"
	@echo "  $(YELLOW)migration-create$(NC)   Create a new migration (NAME=xxx)"
	@echo "  $(YELLOW)dev$(NC)                Start development server"
	@echo "  $(YELLOW)lint$(NC)               Run linting"
	@echo "  $(YELLOW)test$(NC)               Run tests"
	@echo "  $(YELLOW)docker-build$(NC)       Build Docker image"
	@echo "  $(YELLOW)clean$(NC)              Clean up caches"
	@echo "  $(YELLOW)health$(NC)             Health check"
	@echo ""

# ============================================================
# 依赖安装
# ============================================================

.PHONY: install
install:
	@echo "$(GREEN)Installing dependencies for pingpong-service...$(NC)"
	@uv sync --all-extras --all-packages

# ============================================================
# 数据库迁移
# ============================================================

.PHONY: migrate
migrate: migrate-up

.PHONY: migrate-up
migrate-up:
	@echo "$(GREEN)Running migrations for pingpong-service...$(NC)"
	@$(ALEMBIC) upgrade head

.PHONY: migrate-down
migrate-down:
	@echo "$(YELLOW)Downgrading last migration...$(NC)"
	@$(ALEMBIC) downgrade -1

.PHONY: migration-create
migration-create:
ifndef NAME
	@echo "$(RED)Error: NAME is required. Usage: make migration-create NAME=initial OR make migration-create NAME=add_xxx_field$(NC)"
	@exit 1
endif
	@echo "$(GREEN)Creating migration: $(NAME)$(NC)"
	@$(ALEMBIC) revision --autogenerate -m "$(NAME)"

.PHONY: migration-show
migration-show:
	@$(ALEMBIC) current
	@$(ALEMBIC) history --verbose

.PHONY: migration-check
migration-check:
	@echo "$(GREEN)Checking migration status...$(NC)"
	@$(ALEMBIC) check

# ============================================================
# 开发服务器
# ============================================================

# 默认端口
PORT ?= 8002
# .env 文件路径（相对于 account-service 目录）
ENV_FILE ?= .env
# 如果 .env 文件存在则设置 ENV_FILE 环境变量
ENV_FILE_ARG := $(shell [ -f $(ENV_FILE) ] && echo "--env-file $(ENV_FILE)" || echo "")

.PHONY: dev
dev:
	@echo "$(GREEN)Starting pingpong-service development server on port $(PORT)...$(NC)"
	@PYTHONPATH=src uvicorn pingpong_service.main:app --port $(PORT) --host 0.0.0.0 $(ENV_FILE_ARG) \
		--reload \
		--reload-dir ../


# ============================================================
# 代码检查
# ============================================================

.PHONY: lint
lint:
	@echo "$(GREEN)Running linting...$(NC)"
	@ruff check src/
	@mypy src/ || true

.PHONY: format
format:
	@echo "$(GREEN)Formatting code...$(NC)"
	@ruff check src/ --fix
	@ruff format src/

# ============================================================
# 测试
# ============================================================

.PHONY: test
test:
	@echo "$(GREEN)Running tests...$(NC)"
	@python -m pytest tests/ -v

.PHONY: test-unit
test-unit:
	@echo "$(GREEN)Running unit tests...$(NC)"
	@python -m pytest tests/unit/ -v

.PHONY: test-integration
test-integration:
	@echo "$(GREEN)Running integration tests...$(NC)"
	@python -m pytest tests/integration/ -v

.PHONY: test-cov
test-cov:
	@echo "$(GREEN)Running tests with coverage...$(NC)"
	@python -m pytest tests/ -v --cov=src --cov-report=html --cov-report=xml

# ============================================================
# Docker
# ============================================================

.PHONY: docker-build
docker-build:
	@echo "$(GREEN)Building Docker image...$(NC)"
	@docker build -t pingpong-service:latest .

.PHONY: docker-run
docker-run:
	@echo "$(GREEN)Running Docker container...$(NC)"
	@docker run -p 8001:8001 --env-file .env pingpong-service:latest

# ============================================================
# 清理
# ============================================================

.PHONY: clean
clean:
	@echo "$(YELLOW)Cleaning up...$(NC)"
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name "*.pyo" -delete 2>/dev/null || true
	@echo "$(GREEN)Clean complete!$(NC)"

# ============================================================
# 健康检查
# ============================================================

.PHONY: health
health:
	@echo "$(GREEN)Checking health of pingpong-service...$(NC)"
	@curl -s -o /dev/null -w "HTTP %{http_code}" http://localhost:8001/health || echo "DOWN"

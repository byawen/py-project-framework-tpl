# ============================================================
# Worker - 本地开发命令 (无 API、无端口)
# ============================================================

# 颜色定义
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[1;33m
BLUE := \033[0;34m
NC := \033[0m # No Color

# Alembic 配置 (注入 src 以便 env.py 导入模块与 models)
ALEMBIC := PYTHONPATH=src uv run --project . alembic -c alembic.ini

# 帮助信息
.PHONY: help
help:
	@echo ""
	@echo "$(BLUE)╔═══════════════════════════════════════════════════════════════╗$(NC)"
	@echo "$(BLUE)║                   Worker - Development Commands               ║$(NC)"
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
	@echo "  $(YELLOW)dev$(NC)                Start the worker (consume tasks)"
	@echo "  $(YELLOW)dev-watch$(NC)          Start with auto-reload on code changes"
	@echo "  $(YELLOW)lint$(NC)               Run linting"
	@echo "  $(YELLOW)test$(NC)               Run tests"
	@echo "  $(YELLOW)docker-build$(NC)       Build Docker image"
	@echo "  $(YELLOW)clean$(NC)              Clean up caches"
	@echo ""

# ============================================================
# 依赖安装
# ============================================================

.PHONY: install
install:
	@echo "$(GREEN)Installing dependencies for pingpong-worker...$(NC)"
	@uv sync --all-extras --all-packages

# ============================================================
# 数据库迁移
# ============================================================

.PHONY: migrate
migrate: migrate-up

.PHONY: migrate-up
migrate-up:
	@echo "$(GREEN)Running migrations for pingpong-worker...$(NC)"
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
# 启动 Worker
# ============================================================

# .env 文件路径
ENV_FILE ?= .env

.PHONY: dev
dev:
	@echo "$(GREEN)Starting pingpong-worker...$(NC)"
	@PYTHONPATH=src python -m pingpong_worker.main

.PHONY: dev-watch
dev-watch:
	@echo "$(GREEN)Starting pingpong-worker (watch mode)...$(NC)"
	@PYTHONPATH=src uv run --project . watchfiles --filter python "python -m pingpong_worker.main" src/

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
	@PYTHONPATH=src python -m pytest tests/ -v

.PHONY: test-cov
test-cov:
	@echo "$(GREEN)Running tests with coverage...$(NC)"
	@PYTHONPATH=src python -m pytest tests/ -v --cov=src --cov-report=html --cov-report=xml

# ============================================================
# Docker
# ============================================================

.PHONY: docker-build
docker-build:
	@echo "$(GREEN)Building Docker image...$(NC)"
	@docker build -t pingpong-worker:latest .

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
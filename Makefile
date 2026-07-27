# ============================================================
# 工程化入口
# ============================================================

# 颜色定义
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[1;33m
BLUE := \033[0;34m
NC := \033[0m # No Color

# 动态获取所有有 Makefile 的服务（兼容 macOS 和 Linux）
define GET_SERVICES
$(shell for dir in services/*/; do [ -f "$$dir/Makefile" ] && echo "$$dir" | sed 's|services/||' | sed 's|/||'; done | sort)
endef

# 帮助信息
.PHONY: help
help:
	@echo ""
	@echo "$(BLUE)╔═══════════════════════════════════════════════════════════════╗$(NC)"
	@echo "$(BLUE)║                    Development Commands                       ║$(NC)"
	@echo "$(BLUE)╚═══════════════════════════════════════════════════════════════╝$(NC)"
	@echo ""
	@echo "$(GREEN)Usage:$(NC)"
	@echo "  make $(YELLOW)<target>$(NC) [SERVICE=<service-name>] [ARGS='...']"
	@echo ""
	@echo "$(GREEN)Service-Specific Targets:$(NC)"
	@echo "  $(YELLOW)install-service$(NC)        Install dependencies for a service"
	@echo "  $(YELLOW)lint-service$(NC)           Run linting for a service"
	@echo "  $(YELLOW)test-service$(NC)           Run tests for a service"
	@echo "  $(YELLOW)migrate-service$(NC)       Run migrations for a service"
	@echo "  $(YELLOW)dev$(NC)                   Start development server"
	@echo "  $(YELLOW)docker-build-service$(NC)   Build Docker image for a service"
	@echo ""
	@echo "$(GREEN)Workspace Management:$(NC)"
	@echo "  $(YELLOW)add-service$(NC)            Add a service to workspace"
	@echo "  $(YELLOW)remove-service$(NC)        Remove a service from workspace"
	@echo ""
	@echo "$(GREEN)All Services Targets:$(NC)"
	@echo "  $(YELLOW)install$(NC)                Install all dependencies"
	@echo "  $(YELLOW)lint$(NC)                  Run linting on all services"
	@echo "  $(YELLOW)test$(NC)                  Run all tests"
	@echo "  $(YELLOW)migrate$(NC)               Run all migrations"
	@echo "  $(YELLOW)docker-build$(NC)          Build all Docker images"
	@echo "  $(YELLOW)compose-up$(NC)            Start all services with docker-compose"
	@echo "  $(YELLOW)compose-down$(NC)          Stop all services"
	@echo "  $(YELLOW)clean$(NC)                 Clean up generated files"
	@echo ""
	@echo "$(GREEN)All-in-One Targets:$(NC)"
	@echo "  $(YELLOW)all-in-one$(NC)           Start All-in-One mode (development)"
	@echo "  $(YELLOW)all-in-one-prod$(NC)       Start All-in-One mode (production)"
	@echo "  $(YELLOW)all-in-one-install$(NC)    Install All-in-One dependencies"
	@echo ""
	@echo "$(GREEN)Worker-in-One Targets:$(NC)"
	@echo "  $(YELLOW)worker-in-one$(NC)         Start Worker-in-One mode (development)"
	@echo "  $(YELLOW)worker-in-one-install$(NC) Install Worker-in-One dependencies"
	@echo ""
	@echo "$(GREEN)Code Generation:$(NC)"
	@echo "  $(YELLOW)generate-service$(NC)      Generate a new service (API + port)"
	@echo "  $(YELLOW)generate-worker$(NC)       Generate a new worker (no API, no port)"
	@echo ""
	@echo "$(GREEN)Examples:$(NC)"
	@echo "  make dev SERVICE=pingpong-service"
	@echo "  make migrate-service SERVICE=pingpong-service"
	@echo "  make lint-service SERVICE=pingpong-service"
	@echo "  make test-service SERVICE=pingpong-service"
	@echo "  make add-service SERVICE=pingpong-service"
	@echo "  make remove-service SERVICE=pingpong-service"
	@echo "  make generate-service SERVICE=new-app SHORT_PREFIX=na PORT=8001"
	@echo "  make generate-worker WORKER=new-app SHORT_PREFIX=na"
	@echo ""
	@echo "$(GREEN)Available Services:$(NC)"
	@for service in $(GET_SERVICES); do \
		echo "  - $$service"; \
	done
	@echo ""

# ============================================================
# 批量操作（遍历所有有 Makefile 的服务）
# ============================================================

.PHONY: install
install:
	@echo "$(GREEN)Installing dependencies for all services...$(NC)"
	@for service in $(GET_SERVICES); do \
		echo "$(BLUE)>>> Installing $$service$(NC)"; \
		$(MAKE) -C services/$$service install || true; \
	done
	@echo "$(GREEN)All dependencies installed!$(NC)"

.PHONY: lint
lint:
	@echo "$(GREEN)Running linting on all services...$(NC)"
	@for service in $(GET_SERVICES); do \
		echo "$(BLUE)>>> Linting $$service$(NC)"; \
		$(MAKE) -C services/$$service lint || true; \
	done
	@echo "$(GREEN)Linting complete!$(NC)"

.PHONY: test
test:
	@echo "$(GREEN)Running all tests...$(NC)"
	@for service in $(GET_SERVICES); do \
		echo "$(BLUE)>>> Testing $$service$(NC)"; \
		$(MAKE) -C services/$$service test || true; \
	done

.PHONY: migrate
migrate:
	@echo "$(GREEN)Running migrations for all services...$(NC)"
	@for service in $(GET_SERVICES); do \
		echo "$(BLUE)>>> Migrating $$service$(NC)"; \
		$(MAKE) -C services/$$service migrate || true; \
	done

.PHONY: docker-build
docker-build:
	@echo "$(GREEN)Building all Docker images...$(NC)"
	@for service in $(GET_SERVICES); do \
		echo "$(BLUE)>>> Building $$service$(NC)"; \
		$(MAKE) -C services/$$service docker-build || true; \
	done

.PHONY: clean
clean:
	@echo "$(YELLOW)Cleaning up generated files and caches...$(NC)"
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name "*.pyo" -delete 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@echo "$(GREEN)Clean complete!$(NC)"

.PHONY: clean-all
clean-all: clean
	@echo "$(YELLOW)Removing all dependencies...$(NC)"
	@rm -rf .venv 2>/dev/null || true

# ============================================================
# 工作区管理
# ============================================================

.PHONY: add-service
add-service:
ifndef SERVICE
	@echo "$(RED)Error: SERVICE is required. Usage: make add-service SERVICE=pingpong-service$(NC)"
	@exit 1
endif
	@echo "$(GREEN)Adding service $(SERVICE) to workspace...$(NC)"
	@uv add --editable ./services/$(SERVICE)

.PHONY: remove-service
remove-service:
ifndef SERVICE
	@echo "$(RED)Error: SERVICE is required. Usage: make remove-service SERVICE=pingpong-service$(NC)"
	@exit 1
endif
	@echo "$(GREEN)Removing service $(SERVICE) from workspace...$(NC)"
	@uv remove $(SERVICE)

# ============================================================
# 单服务操作（调用服务目录下的 Makefile）
# ============================================================

.PHONY: install-service
install-service:
ifndef SERVICE
	@echo "$(RED)Error: SERVICE is required. Usage: make install-service SERVICE=pingpong-service$(NC)"
	@exit 1
endif
	$(MAKE) -C services/$(SERVICE) install

.PHONY: lint-service
lint-service:
ifndef SERVICE
	@echo "$(RED)Error: SERVICE is required. Usage: make lint-service SERVICE=pingpong-service$(NC)"
	@exit 1
endif
	$(MAKE) -C services/$(SERVICE) lint

.PHONY: test-service
test-service:
ifndef SERVICE
	@echo "$(RED)Error: SERVICE is required. Usage: make test-service SERVICE=pingpong-service$(NC)"
	@exit 1
endif
	$(MAKE) -C services/$(SERVICE) test

.PHONY: migrate-service
migrate-service:
ifndef SERVICE
	@echo "$(RED)Error: SERVICE is required. Usage: make migrate-service SERVICE=pingpong-service$(NC)"
	@exit 1
endif
	$(MAKE) -C services/$(SERVICE) migrate

.PHONY: migration-create
migration-create:
ifndef SERVICE
	@echo "$(RED)Error: SERVICE is required. Usage: make migration-create SERVICE=pingpong-service NAME=add_user_field$(NC)"
	@exit 1
endif
ifndef NAME
	@echo "$(RED)Error: NAME is required. Usage: make migration-create SERVICE=pingpong-service NAME=add_user_field$(NC)"
	@exit 1
endif
	$(MAKE) -C services/$(SERVICE) migration-create NAME="$(NAME)"

.PHONY: dev
dev:
ifndef SERVICE
	@echo "$(RED)Error: SERVICE is required. Usage: make dev SERVICE=pingpong-service$(NC)"
	@exit 1
endif
	$(MAKE) -C services/$(SERVICE) dev

.PHONY: dev-https
dev-https:
ifndef SERVICE
	@echo "$(RED)Error: SERVICE is required.$(NC)"
	@exit 1
endif
	$(MAKE) -C services/$(SERVICE) dev-https

.PHONY: docker-build-service
docker-build-service:
ifndef SERVICE
	@echo "$(RED)Error: SERVICE is required.$(NC)"
	@exit 1
endif
	$(MAKE) -C services/$(SERVICE) docker-build

# ============================================================
# All-in-One 模式 (使用 services 下的服务模块)
# ============================================================

# 服务目录列表
COMMON_SRC := $(PWD)/services/common/src
PINGPONG_SRC := $(PWD)/services/pingpong-service/src

.PHONY: all-in-one
all-in-one:
	@echo "$(GREEN)Starting All-in-One mode...$(NC)"
	@cd all-in-one && PYTHONPATH="$(COMMON_SRC):$(PINGPONG_SRC):$(PWD)/all-in-one/src:$$PYTHONPATH" uv run uvicorn src.all_in_one.main:app \
		--reload \
		--reload-dir ../services/ \
		--reload-dir ../all-in-one/src \
		--port 8002 --host 0.0.0.0

.PHONY: all-in-one-prod
all-in-one-prod:
	@echo "$(GREEN)Starting All-in-One mode (production)...$(NC)"
	@cd all-in-one && PYTHONPATH="$(COMMON_SRC):$(PINGPONG_SRC):$(PWD)/all-in-one/src:$$PYTHONPATH" uv run gunicorn src.all_in_one.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

.PHONY: all-in-one-install
all-in-one-install:
	@echo "$(GREEN)Installing All-in-One dependencies...$(NC)"
	@cd all-in-one && uv sync --frozen

.PHONY: all-in-one-add
all-in-one-add:
	@echo "$(GREEN)Adding all-in-one to workspace...$(NC)"
	@uv sync

.PHONY: all-in-one-remove
all-in-one-remove:
	@echo "$(GREEN)Removing all-in-one from workspace...$(NC)"
	@echo "$(YELLOW)all-in-one is a workspace member, please remove it manually from pyproject.toml [tool.uv.workspace.members]$(NC)"

# ============================================================
# Worker-in-One 模式 (使用 workers 下的 worker 模块)
# ============================================================

.PHONY: worker-in-one
worker-in-one:
	@echo "$(GREEN)Starting Worker-in-One mode...$(NC)"
	@cd worker-in-one && PYTHONPATH="$(COMMON_SRC):$(PINGPONG_SRC):$(PWD)/workers/pingpong-worker/src:$(PWD)/worker-in-one/src:$$PYTHONPATH" uv run python -m worker_in_one.main

.PHONY: worker-in-one-install
worker-in-one-install:
	@echo "$(GREEN)Installing Worker-in-One dependencies...$(NC)"
	@cd worker-in-one && uv sync --frozen

# ============================================================
# Docker Compose
# ============================================================

.PHONY: compose-up
compose-up:
	@docker-compose -f infrastructure/docker-compose.yml up -d

.PHONY: compose-up-dev
compose-up-dev:
	@docker-compose -f infrastructure/docker-compose.yml -f infrastructure/docker-compose.dev.yml up -d

.PHONY: compose-down
compose-down:
	@docker-compose -f infrastructure/docker-compose.yml down

.PHONY: compose-logs
compose-logs:
	@docker-compose -f infrastructure/docker-compose.yml logs -f

.PHONY: compose-logs-service
compose-logs-service:
ifndef SERVICE
	@echo "$(RED)Error: SERVICE is required.$(NC)"
	@exit 1
endif
	@docker-compose -f infrastructure/docker-compose.yml logs -f $(SERVICE)

# ============================================================
# Kubernetes
# ============================================================

.PHONY: k8s-apply
k8s-apply:
	@kubectl apply -f infrastructure/kubernetes/

.PHONY: k8s-delete
k8s-delete:
	@kubectl delete -f infrastructure/kubernetes/

.PHONY: k8s-logs
k8s-logs:
ifndef SERVICE
	@echo "$(RED)Error: SERVICE is required.$(NC)"
	@exit 1
endif
	@kubectl logs -f deployment/$(SERVICE) -n app-service

# ============================================================
# 代码生成
# ============================================================

.PHONY: generate-service
generate-service:
ifndef SERVICE
	@echo "$(RED)Error: SERVICE is required. Usage: make generate-service SERVICE=new-app SHORT_PREFIX=na [PORT=8001]$(NC)"
	@exit 1
endif
ifndef SHORT_PREFIX
	@echo "$(RED)Error: SHORT_PREFIX is required. Usage: make generate-service SERVICE=new-app SHORT_PREFIX=na [PORT=8001]$(NC)"
	@exit 1
endif
	@echo "$(GREEN)Generating new service: $(SERVICE) with prefix $(SHORT_PREFIX)$(NC)"
ifndef PORT
	@python3 scripts/generate-service/generate_service.py $(SERVICE) $(SHORT_PREFIX)
else
	@python3 scripts/generate-service/generate_service.py $(SERVICE) $(SHORT_PREFIX) $(PORT)
endif

.PHONY: generate-worker
generate-worker:
ifndef WORKER
	@echo "$(RED)Error: WORKER is required. Usage: make generate-worker WORKER=new-app SHORT_PREFIX=na$(NC)"
	@exit 1
endif
ifndef SHORT_PREFIX
	@echo "$(RED)Error: SHORT_PREFIX is required. Usage: make generate-worker WORKER=new-app SHORT_PREFIX=na$(NC)"
	@exit 1
endif
	@echo "$(GREEN)Generating new worker: $(WORKER) with prefix $(SHORT_PREFIX)$(NC)"
	@python3 scripts/generate-service/generate_worker.py $(WORKER) $(SHORT_PREFIX)

# ============================================================
# 健康检查
# ============================================================

.PHONY: health
health:
	@for service in $(GET_SERVICES); do \
		$(MAKE) -C services/$$service health || true; \
	done

# ============================================================
# 文档
# ============================================================

.PHONY: docs
docs:
	@for service in $(GET_SERVICES); do \
		$(MAKE) -C services/$$service docs || true; \
	done

# ============================================================
# 服务列表
# ============================================================

.PHONY: services
services:
	@echo "$(GREEN)Available services:$(NC)"
	@for service in $(GET_SERVICES); do \
		echo "  - $$service"; \
	done

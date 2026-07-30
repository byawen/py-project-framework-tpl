#!/usr/bin/env bash
# 在 deploy-all-in-one 容器内运行所有服务的数据库迁移
set -euo pipefail

CONTAINER="${CONTAINER:-deploy-all-in-one}"
RESTART_CONTAINER="${RESTART_CONTAINER:-false}"

echo "==> Running database migrations in container: ${CONTAINER}"

# 从容器的运行环境中读取 DATABASE_URL
DB_URL="$(docker exec "${CONTAINER}" printenv DATABASE_URL 2>/dev/null || true)"

if [[ -z "${DB_URL}" ]]; then
  echo "ERROR: cannot read DATABASE_URL from container '${CONTAINER}'" >&2
  echo "Make sure the container is running and has DATABASE_URL set." >&2
  exit 1
fi

echo "==> Using DATABASE_URL: ${DB_URL}"

run_migration() {
  local service_dir="$1"
  local service_name="$2"
  echo ""
  echo "--- Migrating: ${service_name} ---"
  docker exec \
    -e DATABASE_URL="${DB_URL}" \
    -w "/workspace/${service_dir}" \
    "${CONTAINER}" \
    alembic upgrade head
  echo "--- Done: ${service_name} ---"
}

# 按依赖顺序运行迁移
run_migration "services/pingpong-service"           "pingpong-service"

echo ""
echo "==> All migrations completed successfully!"

if [[ "${RESTART_CONTAINER}" == "true" ]]; then
  echo "==> Restarting container: ${CONTAINER}"
  docker restart "${CONTAINER}" >/dev/null
  echo "==> Container restarted: ${CONTAINER}"
else
  echo "==> Skip container restart (RESTART_CONTAINER=${RESTART_CONTAINER})"
fi

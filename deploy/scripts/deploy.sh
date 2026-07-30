#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

TAG="${TAG:-$(date +%Y%m%d%H%M%S)}"

# Run mode: local only.
# You should ssh/login into the target machine and run this script there.
REMOTE_APP_DIR="${REMOTE_APP_DIR:-${HOME}/.deploy-service}"

ENV_ALL_IN_ONE_FILE="${ENV_ALL_IN_ONE_FILE:-${REPO_ROOT}/deploy/config/all-in-one.env}"
ENV_WORKER_IN_ONE_FILE="${ENV_WORKER_IN_ONE_FILE:-${REPO_ROOT}/deploy/config/worker-in-one.env}"

# Services to operate on.
# Space-separated list. Supported: all-in-one, worker-in-one
SERVICES="${SERVICES:-all-in-one}"

ALL_IN_ONE_HTTP_PORT="${ALL_IN_ONE_HTTP_PORT:-8001}"

# All-in-One 容器名称
CONTAINER_NAME="${CONTAINER_NAME:-deploy-all-in-one}"
# Worker-in-One 容器名称
WORKER_IN_ONE_CONTAINER_NAME="${WORKER_IN_ONE_CONTAINER_NAME:-deploy-worker-in-one}"

PYTHON_BASE_IMAGE="${PYTHON_BASE_IMAGE:-python:3.12-slim}"

# Dockerfile to use
DOCKERFILE="${DOCKERFILE:-Dockerfile.all-in-one}"
WORKER_IN_ONE_DOCKERFILE="${WORKER_IN_ONE_DOCKERFILE:-Dockerfile.worker-in-one}"

# 每个服务最多保留历史镜像数量
IMAGE_RETENTION_COUNT="${IMAGE_RETENTION_COUNT:-2}"

# 容器资源限制（4核8G 服务器建议：CPU 5 核 / 内存 9g，留余量给系统与 Docker）
CONTAINER_CPU_LIMIT="${CONTAINER_CPU_LIMIT:-2}"
CONTAINER_MEMORY_LIMIT="${CONTAINER_MEMORY_LIMIT:-2g}"
WORKER_IN_ONE_CONTAINER_CPU_LIMIT="${WORKER_IN_ONE_CONTAINER_CPU_LIMIT:-2}"
WORKER_IN_ONE_CONTAINER_MEMORY_LIMIT="${WORKER_IN_ONE_CONTAINER_MEMORY_LIMIT:-2g}"

# 健康检查重试配置
HEALTHCHECK_RETRIES="${HEALTHCHECK_RETRIES:-30}"
HEALTHCHECK_INTERVAL="${HEALTHCHECK_INTERVAL:-2}"
HEALTHCHECK_BLOCKING="${HEALTHCHECK_BLOCKING:-false}"

has_service() {
  local s="$1"
  [[ " ${SERVICES} " == *" ${s} "* ]]
}

require_file() {
  local f="$1"
  if [[ ! -f "${f}" ]]; then
    echo "Missing file: ${f}" >&2
    exit 1
  fi
}

load_env() {
  local f="$1"
  require_file "${f}"
  set -a
  # shellcheck disable=SC1090
  source "${f}"
  set +a
}

bundle_images() {
  local out="$1"
  local images=()

  if has_service all-in-one; then
    require_file "${ENV_ALL_IN_ONE_FILE}"
    echo "Building with ${DOCKERFILE}..."
    docker build \
      -f "${REPO_ROOT}/deploy/${DOCKERFILE}" \
      --build-arg "PYTHON_BASE_IMAGE=${PYTHON_BASE_IMAGE}" \
      -t "deploy-all-in-one:${TAG}" \
      "${REPO_ROOT}"
    images+=("deploy-all-in-one:${TAG}")
  fi

  if has_service worker-in-one; then
    require_file "${ENV_WORKER_IN_ONE_FILE}"
    echo "Building with ${WORKER_IN_ONE_DOCKERFILE}..."
    docker build \
      -f "${REPO_ROOT}/deploy/${WORKER_IN_ONE_DOCKERFILE}" \
      --build-arg "PYTHON_BASE_IMAGE=${PYTHON_BASE_IMAGE}" \
      -t "deploy-worker-in-one:${TAG}" \
      "${REPO_ROOT}"
    images+=("deploy-worker-in-one:${TAG}")
  fi

  if [[ ${#images[@]} -eq 0 ]]; then
    echo "No services selected (SERVICES='${SERVICES}')" >&2
    exit 1
  fi

  if [[ -n "${out}" ]]; then
    docker save "${images[@]}" | gzip -c > "${out}"
  fi
}

local_healthcheck() {
  local health_url="http://127.0.0.1:${ALL_IN_ONE_HTTP_PORT}/health"
  local retries="${HEALTHCHECK_RETRIES}"
  local interval="${HEALTHCHECK_INTERVAL}"

  if ! [[ "${retries}" =~ ^[0-9]+$ ]] || [[ "${retries}" -lt 1 ]]; then
    retries=30
  fi
  if ! [[ "${interval}" =~ ^[0-9]+$ ]] || [[ "${interval}" -lt 1 ]]; then
    interval=2
  fi

  local has_container_health="false"
  if [[ "$(docker inspect -f '{{if .State.Health}}yes{{else}}no{{end}}' "${CONTAINER_NAME}" 2>/dev/null || echo no)" == "yes" ]]; then
    has_container_health="true"
  fi

  echo "Healthcheck: ${health_url}, retries=${retries}, interval=${interval}s"

  for ((i = 1; i <= retries; i++)); do
    if [[ "${has_container_health}" == "true" ]]; then
      local health_status
      health_status="$(docker inspect -f '{{.State.Health.Status}}' "${CONTAINER_NAME}" 2>/dev/null || echo unknown)"

      if [[ "${health_status}" == "healthy" ]]; then
        echo "All-in-One container health status: healthy"
        return 0
      fi

      if [[ "${health_status}" == "unhealthy" ]]; then
        echo "Container health status is unhealthy" >&2
        docker logs --tail 200 "${CONTAINER_NAME}" || true
        return 1
      fi

      echo "Healthcheck retry ${i}/${retries} status=${health_status}, waiting ${interval}s..."
    else
      if curl -fsS "${health_url}" >/dev/null 2>&1; then
        echo "All-in-One healthcheck OK"
        return 0
      fi
      echo "Healthcheck retry ${i}/${retries} failed, waiting ${interval}s..."
    fi

    sleep "${interval}"
  done

  echo "Healthcheck failed after ${retries} retries: ${health_url}" >&2
  docker logs --tail 200 "${CONTAINER_NAME}" || true
  return 1
}

worker_in_one_healthcheck() {
  local retries="${HEALTHCHECK_RETRIES}"
  local interval="${HEALTHCHECK_INTERVAL}"

  if ! [[ "${retries}" =~ ^[0-9]+$ ]] || [[ "${retries}" -lt 1 ]]; then
    retries=30
  fi
  if ! [[ "${interval}" =~ ^[0-9]+$ ]] || [[ "${interval}" -lt 1 ]]; then
    interval=2
  fi

  echo "Worker-in-One healthcheck: container=${WORKER_IN_ONE_CONTAINER_NAME}, retries=${retries}, interval=${interval}s"

  local has_container_health="false"
  if [[ "$(docker inspect -f '{{if .State.Health}}yes{{else}}no{{end}}' "${WORKER_IN_ONE_CONTAINER_NAME}" 2>/dev/null || echo no)" == "yes" ]]; then
    has_container_health="true"
  fi

  for ((i = 1; i <= retries; i++)); do
    if [[ "${has_container_health}" == "true" ]]; then
      local health_status
      health_status="$(docker inspect -f '{{.State.Health.Status}}' "${WORKER_IN_ONE_CONTAINER_NAME}" 2>/dev/null || echo unknown)"

      if [[ "${health_status}" == "healthy" ]]; then
        echo "Worker-in-One container health status: healthy"
        return 0
      fi

      if [[ "${health_status}" == "unhealthy" ]]; then
        echo "Worker-in-One container health status is unhealthy" >&2
        docker logs --tail 200 "${WORKER_IN_ONE_CONTAINER_NAME}" || true
        return 1
      fi

      echo "Worker-in-One healthcheck retry ${i}/${retries} status=${health_status}, waiting ${interval}s..."
    else
      # Worker 进程无 HTTP 端口，检查容器运行状态即可
      local container_status
      container_status="$(docker inspect -f '{{.State.Running}}' "${WORKER_IN_ONE_CONTAINER_NAME}" 2>/dev/null || echo false)"
      if [[ "${container_status}" == "true" ]]; then
        echo "Worker-in-One container is running"
        return 0
      fi
      echo "Worker-in-One healthcheck retry ${i}/${retries} failed, waiting ${interval}s..."
    fi

    sleep "${interval}"
  done

  echo "Worker-in-One healthcheck failed after ${retries} retries" >&2
  docker logs --tail 200 "${WORKER_IN_ONE_CONTAINER_NAME}" || true
  return 1
}

cleanup_old_images() {
  local image_repo="$1"
  local keep_count="$2"

  if ! [[ "${keep_count}" =~ ^[0-9]+$ ]] || [[ "${keep_count}" -lt 1 ]]; then
    echo "Invalid IMAGE_RETENTION_COUNT=${keep_count}, skip cleanup"
    return
  fi

  local -a image_lines=()
  local line
  while IFS= read -r line; do
    [[ -n "${line}" ]] && image_lines+=("${line}")
  done < <(
    docker image ls "${image_repo}" --no-trunc --format '{{.ID}} {{.Repository}}:{{.Tag}}' \
      | awk '$2 !~ /:<none>$/ {print}'
  )

  local total=${#image_lines[@]}
  if [[ ${total} -le ${keep_count} ]]; then
    echo "No old images to clean for ${image_repo} (total=${total}, keep=${keep_count})"
    return
  fi

  local -a old_refs=()
  local -a old_ids=()
  local i

  for i in "${!image_lines[@]}"; do
    if [[ $((i + 1)) -le ${keep_count} ]]; then
      continue
    fi

    line="${image_lines[$i]}"
    local image_id="${line%% *}"
    local image_ref="${line#* }"

    old_refs+=("${image_ref}")
    old_ids+=("${image_id}")
  done

  echo "Cleaning old images for ${image_repo} (keep latest ${keep_count}):"
  printf '  - %s\n' "${old_refs[@]}"

  for ref in "${old_refs[@]}"; do
    docker image rm -f "${ref}" || true
  done

  # 二次兜底：某些 tag 删除后镜像仍被其他 tag 关联，尝试按 ID 再删一次
  for image_id in "${old_ids[@]}"; do
    if docker image inspect "${image_id}" >/dev/null 2>&1; then
      docker image rm -f "${image_id}" >/dev/null 2>&1 || true
    fi
  done

  echo "Images after cleanup for ${image_repo}:"
  docker image ls "${image_repo}" --format 'table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.CreatedSince}}'
}

remote_stop() {
  if has_service all-in-one; then docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true; fi
  if has_service worker-in-one; then docker rm -f "${WORKER_IN_ONE_CONTAINER_NAME}" >/dev/null 2>&1 || true; fi
  docker ps --filter "name=worker-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
}

remote_status() {
  docker ps --filter 'name=worker-' --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
}

main_deploy() {
  bundle_images ""

  docker network inspect vpc-net >/dev/null 2>&1 || docker network create vpc-net

  if has_service all-in-one; then
    local static_src_dir="${REPO_ROOT}/services/pingpong-service/static"
    local static_target_dir="${REMOTE_APP_DIR}/all-in-one/static"
    local static_backup_dir="${REMOTE_APP_DIR}/all-in-one/static-bak"

    mkdir -p "${REMOTE_APP_DIR}/all-in-one"

    if [[ ! -d "${static_src_dir}" ]]; then
      echo "Warning: static source directory not found, skip static sync: ${static_src_dir}" >&2
    else
      if [[ -d "${static_target_dir}" ]]; then
        echo "Backing up static: ${static_target_dir} -> ${static_backup_dir}"
        rm -rf "${static_backup_dir}"
        cp -a "${static_target_dir}" "${static_backup_dir}"
      else
        echo "No existing static directory found, skip backup: ${static_target_dir}"
      fi

      echo "Syncing static files: ${static_src_dir} -> ${static_target_dir}"
      rm -rf "${static_target_dir}"
      mkdir -p "${static_target_dir}"
      cp -a "${static_src_dir}/." "${static_target_dir}/"
      echo "Static sync completed: ${static_target_dir}"
    fi

    mkdir -p "${REMOTE_APP_DIR}/all-in-one/uploads"
    mkdir -p "${REMOTE_APP_DIR}/all-in-one/logs"
    # bind mount 会覆盖容器内目录权限，需显式设置可写
    chmod 777 "${REMOTE_APP_DIR}/all-in-one/uploads" "${REMOTE_APP_DIR}/all-in-one/logs"

    docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
    docker run -d \
      --name "${CONTAINER_NAME}" \
      --network vpc-net \
      --cpus "${CONTAINER_CPU_LIMIT}" \
      --memory "${CONTAINER_MEMORY_LIMIT}" \
      --env-file "${ENV_ALL_IN_ONE_FILE}" \
      -v "${REMOTE_APP_DIR}/all-in-one/uploads:/workspace/uploads" \
      -v "${REMOTE_APP_DIR}/all-in-one/static:/workspace/all-in-one/static" \
      -v "${REMOTE_APP_DIR}/all-in-one/logs:/workspace/all-in-one/logs" \
      -p "${ALL_IN_ONE_HTTP_PORT}:8001" \
      --restart unless-stopped \
      "deploy-all-in-one:${TAG}"
  fi

  if has_service worker-in-one; then
    mkdir -p "${REMOTE_APP_DIR}/worker-in-one/logs"
    mkdir -p "${REMOTE_APP_DIR}/worker-in-one/temp"
    # bind mount 会覆盖容器内目录权限，需显式设置可写
    chmod 777 "${REMOTE_APP_DIR}/worker-in-one/logs" "${REMOTE_APP_DIR}/worker-in-one/temp"

    docker rm -f "${WORKER_IN_ONE_CONTAINER_NAME}" >/dev/null 2>&1 || true
    docker run -d \
      --name "${WORKER_IN_ONE_CONTAINER_NAME}" \
      --network vpc-net \
      --cpus "${WORKER_IN_ONE_CONTAINER_CPU_LIMIT}" \
      --memory "${WORKER_IN_ONE_CONTAINER_MEMORY_LIMIT}" \
      --env-file "${ENV_WORKER_IN_ONE_FILE}" \
      -v "${REMOTE_APP_DIR}/worker-in-one/logs:/workspace/worker-in-one/logs" \
      -v "${REMOTE_APP_DIR}/worker-in-one/temp:/workspace/worker-in-one/temp" \
      --restart unless-stopped \
      "deploy-worker-in-one:${TAG}"
  fi

  docker ps --filter 'name=deploy-' --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

  if has_service all-in-one; then
    # 先清理旧镜像，避免被健康检查等待阻塞
    cleanup_old_images "deploy-all-in-one" "${IMAGE_RETENTION_COUNT}"

    # HEALTHCHECK_BLOCKING=false 时，不等待健康检查完成，只输出当前状态
    if [[ "${HEALTHCHECK_BLOCKING}" == "true" ]]; then
      if ! local_healthcheck; then
        echo "Healthcheck failed and HEALTHCHECK_BLOCKING=true, abort deploy" >&2
        exit 1
      fi
    else
      current_health_status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${CONTAINER_NAME}" 2>/dev/null || echo unknown)"
      echo "Healthcheck non-blocking mode, current status=${current_health_status}"
    fi
  fi

  if has_service worker-in-one; then
    cleanup_old_images "deploy-worker-in-one" "${IMAGE_RETENTION_COUNT}"

    if [[ "${HEALTHCHECK_BLOCKING}" == "true" ]]; then
      if ! worker_in_one_healthcheck; then
        echo "Worker-in-One healthcheck failed and HEALTHCHECK_BLOCKING=true, abort deploy" >&2
        exit 1
      fi
    else
      current_health_status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${WORKER_IN_ONE_CONTAINER_NAME}" 2>/dev/null || echo unknown)"
      echo "Worker-in-One healthcheck non-blocking mode, current status=${current_health_status}"
    fi
  fi

  echo "Deployed tag=${TAG}"
  if has_service all-in-one; then
    echo "All-in-One: http://localhost:${ALL_IN_ONE_HTTP_PORT}"
    echo "API Docs:   http://localhost:${ALL_IN_ONE_HTTP_PORT}/docs"
  fi
  if has_service worker-in-one; then
    echo "Worker-in-One: container=${WORKER_IN_ONE_CONTAINER_NAME}"
  fi
}

main() {
  local action="${1:-deploy}"

  case "${action}" in
    deploy)
      main_deploy
      ;;
    stop)
      remote_stop
      ;;
    status)
      remote_status
      ;;
    *)
      echo "Usage: $0 [deploy|stop|status]" >&2
      exit 2
      ;;
  esac
}

main "$@"

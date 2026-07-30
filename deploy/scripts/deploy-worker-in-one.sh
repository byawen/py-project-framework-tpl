#!/usr/bin/env bash
set -euo pipefail
SERVICES="worker-in-one" exec "$(cd "$(dirname "$0")" && pwd)/deploy.sh" "$@"
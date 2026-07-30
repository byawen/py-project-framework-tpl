#!/usr/bin/env bash
set -euo pipefail
SERVICES="all-in-one" exec "$(cd "$(dirname "$0")" && pwd)/deploy.sh" "$@"

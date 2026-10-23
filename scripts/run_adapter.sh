#!/usr/bin/env bash
# 启动 QQ 官方机器人适配器（gsuid_core 需已启动）
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo "缺少 .env（QQ_APP_ID / QQ_APP_SECRET）" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1091
source .env
set +a

export CORE_WS_URL="${CORE_WS_URL:-ws://127.0.0.1:8765/ws/qq}"
exec .venv/bin/python -m adapter.main
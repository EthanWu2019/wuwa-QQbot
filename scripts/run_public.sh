#!/usr/bin/env bash
# 公网入口：qqbot.ethanshermes.com 的落地服务
# /img/{hash}.jpg 直接吐图，其余反代给 gsuid_core:8765
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo "缺少 .env" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1091
source .env
set +a

export PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-https://qqbot.ethanshermes.com}"
export CORE_UPSTREAM="${CORE_UPSTREAM:-http://127.0.0.1:8765}"
export IMG_PORT="${IMG_PORT:-8766}"
exec .venv/bin/python -m adapter.imgserver
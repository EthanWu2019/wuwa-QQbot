#!/usr/bin/env bash
# 启动 gsuid_core（鸣潮插件宿主）
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/vendor/gsuid_core:${PYTHONPATH:-}"
exec .venv/bin/python -c "from gsuid_core.core import main; main()"
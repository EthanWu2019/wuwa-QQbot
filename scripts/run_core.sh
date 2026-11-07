#!/usr/bin/env bash
# 启动 gsuid_core（鸣潮插件宿主）
#
# ⚠️ HOST/PORT 是 gsuid_core 的 **命令行参数**，不是 data/config.json 里的字段。
#    core.py:94-99 是 `if args.host: core_config.set_config("HOST", args.host)`，
#    而 CORE_CONFIG 里 HOST 默认写死 "localhost"。只改 config.json 不生效，
#    必须走 argv。Cloudflare Tunnel 能访问到 core 的前提就是这一行。
#    （gsuid_core 没有 __main__.py，所以不能用 -m，要走 sys.argv）
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/vendor/gsuid_core:${PYTHONPATH:-}"

# 启动前自检插件完整性。
# 2026-11-07 事故：插件曾软链到 /tmp，macOS 清 /tmp 后被删光，
# core 只加载 691 个触发器（正常 1680+），机器人全程没反应。
# 这里先跑一遍检查，缺文件就自动从永久副本/上游恢复。
./scripts/check_plugins.sh || {
  echo "[run_core] 插件自检失败，core 可能起不来" >&2
  exit 1
}

CORE_HOST="${CORE_HOST:-0.0.0.0}"
CORE_PORT="${CORE_PORT:-8765}"

exec .venv/bin/python -c 'import sys; from gsuid_core.core import main; sys.argv[1:] = ["--host", sys.argv[1], "--port", sys.argv[2]]; main()' "$CORE_HOST" "$CORE_PORT"
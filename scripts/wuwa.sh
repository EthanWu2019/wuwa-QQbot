#!/usr/bin/env bash
# 鸣潮 QQ 官方机器人服务管理
#
# 三个 launchd 服务：
#   ai.wuwa.core      gsuid_core            *:8765
#   ai.wuwa.public    图床 + 反代           *:8766   ← Cloudflare Tunnel 指向这里
#   ai.wuwa.adapter   QQ 官方网关适配器
#
# 全部 KeepAlive=true，崩溃/被杀自动拉起，开机自启。

set -uo pipefail
LA="$HOME/Library/LaunchAgents"
DIR="$(cd "$(dirname "$0")/.." && pwd)/scripts/launchd"
UID_=$(id -u)

status() {
  printf '\n=== 服务状态 ===\n'
  launchctl list | grep ai.wuwa || echo "（未加载）"
  printf '\n=== 端口 ===\n'
  for p in 8765 8766; do
    if lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1; then
      printf '  %s  LISTEN\n' "$p"
    else
      printf '  %s  DOWN\n' "$p"
    fi
  done
}

load_all() {
  mkdir -p "$LA" "$DIR/logs"
  for f in "$DIR"/*.plist; do
    n=$(basename "$f")
    cp "$f" "$LA/$n"
    launchctl unload "$LA/$n" 2>/dev/null
    launchctl load "$LA/$n"
    printf 'loaded: %s\n' "$n"
  done
}

stop_all() {
  for f in "$LA"/ai.wuwa.*.plist; do
    [ -e "$f" ] || continue
    launchctl unload "$f" 2>/dev/null
    printf 'unloaded: %s\n' "$(basename "$f")"
  done
}

restart_one() {
  launchctl kickstart -k "gui/$UID_/ai.wuwa.$1"
  printf 'restarted: ai.wuwa.%s\n' "$1"
}

logs() {
  tail -n "${2:-30}" "$DIR/logs/$1.log" 2>/dev/null
}

case "${1:-status}" in
  status) status ;;
  load)   load_all; sleep 45; status ;;
  stop)   stop_all ;;
  restart)
    case "${2:-all}" in
      all) for s in core public adapter; do restart_one "$s"; done ;;
      *) restart_one "$2" ;;
    esac
    ;;
  logs)
    case "${2:-adapter}" in
      core)    logs core "${3:-30}" ;;
      public)  logs public "${3:-30}" ;;
      adapter) logs adapter "${3:-30}" ;;
    esac
    ;;
  *) echo "用法: $0 {status|load|stop|restart [core|public|adapter|all]|logs [core|public|adapter] [行数]}" ;;
esac
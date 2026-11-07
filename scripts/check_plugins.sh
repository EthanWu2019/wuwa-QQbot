#!/usr/bin/env bash
# 插件完整性自检 + 自动修复
#
# ⚠️ 历史事故（2026-11-07）：
#   XutheringWavesUID 原先是软链到 /tmp/ww_probe/main —— macOS 会定期
#   清理 /tmp，结果插件目录被清空，core 启动时 14 个模块导入失败，
#   只加载了 691 个触发器（正常 1680+），机器人表现为「完全没反应」
#   （定时签到是广播，不走命令触发器，所以还好使）。
#
#   根因：把插件放在 /tmp 下 + 没纳入版本控制。
#
# 本脚本做两件事：
#   1. 检查插件目录是否完整（关键模块 + 触发器数量下限）
#   2. 发现缺失就从 vendor/plugins_src/ 的永久副本恢复
#
# 用法：
#   scripts/check_plugins.sh          # 检查并自动修复
#   scripts/check_plugins.sh --check  # 只检查不修复

set -uo pipefail
cd "$(dirname "$0")/.."

PLUGINS_DIR="vendor/gsuid_core/gsuid_core/plugins"
WS_SRC="vendor/plugins_src/XutheringWavesUID"
WS_LINK="$PLUGINS_DIR/XutheringWavesUID"
CHECK_ONLY=0
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=1

# 关键模块（缺一个插件就废了一半）
# 注意路径：软链 XutheringWavesUID → 仓库根，仓库根下才有 XutheringWavesUID/ 子目录
REQUIRED=(
  "XutheringWavesUID/XutheringWavesUID/utils/button.py"
  "XutheringWavesUID/XutheringWavesUID/utils/hint.py"
  "XutheringWavesUID/XutheringWavesUID/utils/at_help.py"
  "XutheringWavesUID/XutheringWavesUID/wutheringwaves_help/get_help.py"
  "XutheringWavesUID/XutheringWavesUID/wutheringwaves_period/draw_period.py"
  "XutheringWavesUID/XutheringWavesUID/wutheringwaves_up/pool.py"
  "XutheringWavesUID/XutheringWavesUID/wutheringwaves_wiki/guide.py"
  "XutheringWavesUID/XutheringWavesUID/version.py"
)

echo "=== 插件完整性检查 ==="

# 1. 软链不能指向 /tmp
if [[ -L "$WS_LINK" ]]; then
  TARGET="$(readlink "$WS_LINK")"
  if [[ "$TARGET" == /tmp/* || "$TARGET" == /private/tmp/* ]]; then
    echo "❌ 危险：插件软链指向临时目录 $TARGET"
    if [[ $CHECK_ONLY -eq 0 ]]; then
      echo "   → 改指向永久副本 $WS_SRC"
      rm -f "$WS_LINK"
      ln -s "$PWD/$WS_SRC" "$WS_LINK"
    else
      exit 1
    fi
  else
    echo "✓ 软链指向永久目录：$TARGET"
  fi
fi

# 2. 关键模块齐全
MISSING=0
for f in "${REQUIRED[@]}"; do
  if [[ ! -f "$PLUGINS_DIR/$f" ]]; then
    echo "❌ 缺失: $f"
    MISSING=$((MISSING+1))
  fi
done

# 3. 源码副本可用（用于恢复）
if [[ -d "$WS_SRC" ]]; then
  echo "✓ 永久副本存在：$WS_SRC"
else
  echo "❌ 永久副本不存在：$WS_SRC"
  MISSING=$((MISSING+1))
fi

# 4. 触发器数量下限（防止静默降级）
# 正常 1600+。掉到几百说明插件只加载了一部分 —— 机器人表现为「没反应」。
# 锚点用 core 自己的「启动完成 ... · v0.11.2」那行，往后数触发器。
LOG="logs/core.out.log"
if [[ -f "$LOG" ]]; then
  ANCHOR_LINE=$(grep -an "启动完成.*· v" "$LOG" | tail -1 | cut -d: -f1)
  if [[ -n "$ANCHOR_LINE" ]]; then
    # 触发器加载日志在「启动完成」**之前**（core 先载插件再报完成），
    # 所以从锚点往上找到上一个「开始加载插件」作为起点。
    START_LINE=$(head -n "$ANCHOR_LINE" "$LOG" | grep -an "开始加载插件" | tail -1 | cut -d: -f1)
    if [[ -z "$START_LINE" ]]; then
      START_LINE=$ANCHOR_LINE
    fi
    COUNT=$(tail -n "+${START_LINE}" "$LOG" | head -n "$((ANCHOR_LINE - START_LINE + 1))" | grep -ac "载入.*触发器" || true)
    echo "触发器数量: ${COUNT:-0}（自上次 core 启动起）"
    # 参考值：健康状态单次启动 ≈ 691（10-23 与 11-07 实测一致）。
    # 低于 500 说明插件只加载了一部分 —— 机器人表现为「没反应」。
    # 注意：不要用日志里的累计数当基准，那是跨多次插件重载累加的。
    if [[ "${COUNT:-0}" -lt 500 ]]; then
      echo "❌ 触发器数量过少（<500，健康值约 691），插件可能没加载全"
      MISSING=$((MISSING+1))
    fi
  fi
fi

if [[ $MISSING -eq 0 ]]; then
  echo "✓ 插件完整"
  exit 0
fi

echo ""
if [[ $CHECK_ONLY -eq 1 ]]; then
  echo "❌ 插件不完整（缺 $MISSING 项），需要恢复"
  exit 1
fi

echo "=== 尝试恢复 ==="
if [[ ! -d "$WS_SRC" ]] || [[ ! -f "$WS_SRC/XutheringWavesUID/version.py" ]]; then
  echo "→ 从上游重新克隆到永久目录 $WS_SRC"
  mkdir -p "$(dirname "$WS_SRC")"
  rm -rf "$WS_SRC"
  if ! git clone --depth 1 https://github.com/Loping151/XutheringWavesUID.git "$WS_SRC"; then
    echo "❌ 克隆失败，需要手动检查网络"
    exit 1
  fi
  echo "✓ 克隆完成（上游最新版；如需固定版本：git -C $WS_SRC checkout c445502）"
fi

rm -f "$WS_LINK"
ln -s "$PWD/$WS_SRC" "$WS_LINK"
echo "✓ 已指向 $WS_SRC"

# 重新应用品牌补丁
if [[ -x .venv/bin/python ]]; then
  .venv/bin/python scripts/patch_brand.py
fi

# 再次自检
echo ""
if ./scripts/check_plugins.sh --check; then
  echo ""
  echo "生效步骤："
  echo "  find vendor/gsuid_core/gsuid_core -name __pycache__ -type d -exec rm -rf {} +"
  echo "  ./scripts/wuwa.sh restart core   # 等 ~90s"
  echo "  ./scripts/wuwa.sh restart adapter"
else
  echo "❌ 恢复后自检仍未通过"
  exit 1
fi

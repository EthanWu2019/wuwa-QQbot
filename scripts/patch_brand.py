"""泰缇斯系统 —— 本地补丁集合（可重复执行）。

上游插件/核心更新会覆盖 vendor/ 里的改动，所以每次升级后重跑本脚本。
每项都做成幂等的：已经打过就直接跳过。

用法：
    .venv/bin/python scripts/patch_brand.py           # 全部应用
    .venv/bin/python scripts/patch_brand.py --check   # 只验证
"""

import json
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
VENDOR = ROOT / "vendor" / "gsuid_core"
PLUGIN = VENDOR / "gsuid_core" / "plugins" / "XutheringWavesUID" / "XutheringWavesUID"

BOT_NAME = "泰缇斯系统"
BOT_VERSION = "1.0.0"
BANNER_SUB_TEXT = "这里是黑海岸，你永远的家。"

# 帮助页文件 → 是否同时替换 banner_sub_text（False = 保留该页原副标题）
PAGES = {
    "wutheringwaves_help/get_help.py": True,
    "wutheringwaves_help/change_help.py": False,
    "wutheringwaves_weight/weight_help.py": False,
}


def _read(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _write(p: pathlib.Path, s: str) -> None:
    p.write_text(s, encoding="utf-8")


# ── 1. 版本号 ────────────────────────────────────────────────
def patch_version() -> bool:
    p = PLUGIN / "version.py"
    src = _read(p)
    if not src:
        print("  ✗ version.py 不存在")
        return False
    new = re.sub(
        r'XutheringWavesUID_version\s*=\s*"[^"]*"',
        f'XutheringWavesUID_version = "{BOT_VERSION}"',
        src,
    )
    if new == src:
        print(f"  · 版本号已是 {BOT_VERSION}")
    else:
        _write(p, new)
        print(f"  ✓ 版本号 → {BOT_VERSION}")
    return True


# ── 2. 帮助页机器人名 / 签名 ─────────────────────────────────
def patch_pages() -> bool:
    for rel, with_sub in PAGES.items():
        p = PLUGIN / rel
        src = _read(p)
        if not src:
            print(f"  ✗ {rel} 不存在")
            continue
        orig = src
        src = src.replace('plugin_name="XutheringWavesUID"', f'plugin_name="{BOT_NAME}"')
        if with_sub:
            src = re.sub(r'banner_sub_text="[^"]*"', f'banner_sub_text="{BANNER_SUB_TEXT}"', src)
        if src == orig:
            print(f"  · {rel} 已符合")
        else:
            _write(p, src)
            print(f"  ✓ {rel} ({'名称+签名' if with_sub else '名称'})")
    return True


# ── 3. 帮助页图标圆角（core）─────────────────────────────────
def patch_icon_round() -> bool:
    p = VENDOR / "gsuid_core" / "help" / "draw_new_plugin_help.py"
    src = _read(p)
    if not src:
        print("  ✗ draw_new_plugin_help.py 不存在")
        return False
    if "PLUGIN_ICON_RADIUS_RATIO" in src:
        print("  · 图标圆角已打")
        return True
    if "import os\n" not in src:
        src = src.replace("import re\n", "import os\nimport re\n", 1)
    if "PLUGIN_ICON_RADIUS_RATIO" not in src.split("def ")[0]:
        src = src.replace(
            'TEXT_PATH = Path(__file__).parent / "texture2d"',
            'TEXT_PATH = Path(__file__).parent / "texture2d"\n'
            "\n"
            "# 帮助页 banner 图标圆角比例（泰缇斯系统）。0 = 恢复上游方形。\n"
            'PLUGIN_ICON_RADIUS_RATIO: float = float(os.getenv("HELP_ICON_RADIUS", "0.22"))',
            1,
        )
    src = src.replace(
        "    # 准备计算整体帮助图大小\n    w, h = 120 + 475 * column, footer.height",
        "    # 圆角遮罩（泰缇斯系统）：上游是方形硬贴，四角直角\n"
        "    if PLUGIN_ICON_RADIUS_RATIO > 0:\n"
        "        _r = int(icon_size * PLUGIN_ICON_RADIUS_RATIO)\n"
        "        _mask = Image.new(\"L\", (icon_size, icon_size), 0)\n"
        "        ImageDraw.Draw(_mask).rounded_rectangle(\n"
        "            (0, 0, icon_size - 1, icon_size - 1), radius=_r, fill=255\n"
        "        )\n"
        "        _rc = Image.new(\"RGBA\", (icon_size, icon_size), (0, 0, 0, 0))\n"
        "        _rc.paste(plugin_icon, (0, 0))\n"
        "        _rc.putalpha(_mask)\n"
        "        plugin_icon = _rc\n\n"
        "    # 准备计算整体帮助图大小\n    w, h = 120 + 475 * column, footer.height",
        1,
    )
    _write(p, src)
    print("  ✓ 帮助页图标圆角")
    return True


# ── 4. command_start 支持 / 前缀 ─────────────────────────────
def patch_command_start() -> bool:
    p = ROOT / "vendor" / "gsuid_core" / "data" / "config.json"
    if not p.exists():
        print("  ✗ data/config.json 不存在")
        return False
    d = json.loads(p.read_text(encoding="utf-8"))
    cur = d.get("command_start") or []
    if "/" in cur:
        print("  · command_start 已含 /")
        return True
    # 放最前面，保证先剥 / 再匹配 ww 前缀
    d["command_start"] = ["/"] + [c for c in cur if c != "/"]
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ command_start = {d['command_start']}")
    return True


def check() -> bool:
    print("验证补丁状态：")
    ok = True

    src = _read(PLUGIN / "version.py")
    m = re.search(r'XutheringWavesUID_version\s*=\s*"([^"]*)"', src)
    got = m.group(1) if m else "?"
    ok &= got == BOT_VERSION
    print(f"  {'✓' if got == BOT_VERSION else '✗'} 版本号 {got}")

    for rel in PAGES:
        s = _read(PLUGIN / rel)
        good = f'plugin_name="{BOT_NAME}"' in s
        ok &= good
        print(f"  {'✓' if good else '✗'} {rel}")

    s = _read(VENDOR / "gsuid_core" / "help" / "draw_new_plugin_help.py")
    good = "PLUGIN_ICON_RADIUS_RATIO" in s
    ok &= good
    print(f"  {'✓' if good else '✗'} 图标圆角")

    cfg = ROOT / "vendor" / "gsuid_core" / "data" / "config.json"
    if cfg.exists():
        d = json.loads(cfg.read_text(encoding="utf-8"))
        good = "/" in (d.get("command_start") or [])
        ok &= good
        print(f"  {'✓' if good else '✗'} command_start")

    icon = ROOT / "vendor" / "gsuid_core" / "data" / "XutheringWavesUID" / "show" / "help_icon.png"
    good = icon.exists()
    ok &= good
    print(f"  {'✓' if good else '✗'} 头像 {icon.name}")
    return ok


def main() -> int:
    if "--check" in sys.argv:
        return 0 if check() else 1
    print(f"应用补丁 → {BOT_NAME} v{BOT_VERSION}\n")
    patch_version()
    patch_pages()
    patch_icon_round()
    patch_command_start()
    print("\n生效步骤：")
    print("  find vendor/gsuid_core/gsuid_core -name __pycache__ -type d -exec rm -rf {} +")
    print("  ./scripts/wuwa.sh restart core   # 等 ~60s")
    print("  ./scripts/wuwa.sh restart adapter")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
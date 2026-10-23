"""泰缇斯系统品牌化补丁 —— 改帮助页的 机器人名/版本号/banner 签名。

背景：owner 要求把默认的「XutheringWavesUID 帮助 / v3.7.1 / 漂泊者，欢迎
在这个时代醒来。」换成自己的品牌。版本号不能跟着上游 3.7.1 走——那是上游
插件版本，和我们的实际发布版本无关（我们从 1.0.0 起自己记）。

上游插件更新会覆盖这三个文件，所以改完要重新跑本脚本。
头像不需要改代码：插件有 HelpIconUpload 配置，图片放
vendor/gsuid_core/data/XutheringWavesUID/show/help_icon.png 即生效。

用法：python scripts/patch_branding.py [--check]
"""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "vendor" / "gsuid_core" / "gsuid_core" / "plugins" / "XutheringWavesUID" / "XutheringWavesUID"

BOT_NAME = "泰缇斯系统"
BOT_VERSION = "1.0.0"
BANNER_SUB_TEXT = "这里是黑海岸，你永远的家。"

# 帮助页文件 → 各自的 banner_sub_text 默认值（保持各自语义，只换机器人名/版本）
PAGES = {
    "wutheringwaves_help/get_help.py": "这里是黑海岸，你永远的家。",
    "wutheringwaves_help/change_help.py": None,  # 保持 "面板替换帮助"
    "wutheringwaves_weight/weight_help.py": None,  # 保持原副标题
}


def patch_version() -> bool:
    """版本号：插件 version.py 的 XutheringWavesUID_version 是全局显示源。"""
    p = PLUGIN / "version.py"
    if not p.exists():
        print(f"  ✗ 缺 {p}")
        return False
    src = p.read_text(encoding="utf-8")
    new = re.sub(
        r'XutheringWavesUID_version\s*=\s*"[^"]*"',
        f'XutheringWavesUID_version = "{BOT_VERSION}"',
        src,
    )
    if new != src:
        p.write_text(new, encoding="utf-8")
        print(f"  ✓ version.py → {BOT_VERSION}")
    else:
        print(f"  · version.py 已是 {BOT_VERSION}")
    return True


def patch_page(rel: str, sub_text: str | None) -> bool:
    p = PLUGIN / rel
    if not p.exists():
        print(f"  ✗ 缺 {rel}")
        return False
    src = p.read_text(encoding="utf-8")
    orig = src

    # 机器人名
    src = src.replace('plugin_name="XutheringWavesUID"', f'plugin_name="{BOT_NAME}"')

    # banner 签名（只在主帮助页换，其余保留各自文案）
    if sub_text:
        src = re.sub(
            r'banner_sub_text="[^"]*"',
            f'banner_sub_text="{sub_text}"',
            src,
        )

    if src != orig:
        p.write_text(src, encoding="utf-8")
        what = f'名称+签名' if sub_text else "名称"
        print(f"  ✓ {rel} ({what})")
    else:
        print(f"  · {rel} 已符合")
    return True


def check() -> bool:
    """确认改动还在（上游更新后跑这个）。"""
    ok = True
    vp = PLUGIN / "version.py"
    if vp.exists():
        m = re.search(r'XutheringWavesUID_version\s*=\s*"([^"]*)"', vp.read_text(encoding="utf-8"))
        got = m.group(1) if m else "?"
        flag = "✓" if got == BOT_VERSION else "✗"
        ok &= got == BOT_VERSION
        print(f"  {flag} 版本号: {got} (期望 {BOT_VERSION})")
    for rel in PAGES:
        pp = PLUGIN / rel
        if not pp.exists():
            continue
        s = pp.read_text(encoding="utf-8")
        flag = "✓" if f'plugin_name="{BOT_NAME}"' in s else "✗"
        ok &= flag == "✓"
        print(f"  {flag} {rel}")
    icon = ROOT / "vendor" / "gsuid_core" / "data" / "XutheringWavesUID" / "show" / "help_icon.png"
    flag = "✓" if icon.exists() else "✗"
    ok &= icon.exists()
    print(f"  {flag} 头像 {icon.name}")
    return ok


def main() -> int:
    if "--check" in sys.argv:
        print("检查品牌化状态：")
        return 0 if check() else 1

    print(f"应用品牌化 → {BOT_NAME} v{BOT_VERSION}")
    patch_version()
    for rel, sub in PAGES.items():
        patch_page(rel, sub)
    print("\n重启 core 生效：./scripts/wuwa.sh restart core")
    print("（core 重启后还要重启 adapter，否则 WS session 失效回不来消息）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
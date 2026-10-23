"""
banner 背景候选方案预览 —— 不改配置、不重启，直接出图给主人看。

生成三种裁切方式，各自叠加真实文字（机器人名/版本/签名），
以及左上角圆角头像，模拟最终帮助页 banner 的样子。

用法：.venv/bin/python scripts/preview_banner.py
输出：data/banner_*.jpg
"""

import pathlib
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data"
HELP = (
    ROOT
    / "vendor/gsuid_core/gsuid_core/plugins/XutheringWavesUID/XutheringWavesUID"
    / "wutheringwaves_help"
)
SRC = ROOT / "assets" / "banner_new.png"
REF = HELP / "texture2d" / "banner_bg.jpg"
ICON = (
    ROOT
    / "vendor/gsuid_core/data/XutheringWavesUID/show/help_icon.png"
)

W, H = 1545, 550
NAME = "泰缇斯系统"
VERSION = "v1.0.0"
SUB = "这里是黑海岸，你永远的家。"


def font(size: int) -> ImageFont.FreeTypeFont:
    for p in (
        HELP / "texture2d/fonts" / "SourceHanSansCN-Bold.ttc",
        HELP.parent.parent / "templates/fonts/SourceHanSansCN-Bold.ttc",
    ):
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def fit_fill(im: Image.Image) -> Image.Image:
    """等比缩放铺满后居中裁剪（不留边，但可能切掉主体）。"""
    s = max(W / im.width, H / im.height)
    n = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    return n.crop(((n.width - W) // 2, (n.height - H) // 2, (n.width - W) // 2 + W, (n.height - H) // 2 + H))


def fit_pad(im: Image.Image) -> Image.Image:
    """完整放入 + 左右补暗色留白，主体不被切。"""
    s = min(W / im.width, H / im.height)
    n = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    bg = Image.new("RGB", (W, H), (12, 14, 22))
    bg.paste(n, ((W - n.width) // 2, (H - n.height) // 2))
    return bg


def fit_left(im: Image.Image) -> Image.Image:
    """靠左放置，右侧留白给标题文字。"""
    s = min(W / im.width, H / im.height)
    n = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    bg = Image.new("RGB", (W, H), (12, 14, 22))
    bg.paste(n, (0, 0))
    return bg


def blurred_pad(im: Image.Image) -> Image.Image:
    """主体居中，两侧用自身模糊填充（无硬边）。"""
    s = H / im.height
    n = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    bg = im.resize((W, H), Image.LANCZOS).filter(__import__("PIL.ImageFilter", fromlist=["x"]).GaussianBlur(18))
    bg = bg.resize((W, H))
    if n.width <= W:
        x = (W - n.width) // 2
        bg.paste(n, (x, 0))
    else:
        left = (n.width - W) // 2
        bg.paste(n.crop((left, 0, left + W, H)), (0, 0))
    return bg


def overlay(bg: Image.Image, with_text: bool = True, icon: bool = True) -> Image.Image:
    img = bg.convert("RGBA")
    if icon and ICON.exists():
        size = 128
        ic = Image.open(ICON).convert("RGBA").resize((size, size), Image.LANCZOS)
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=int(size * 0.22), fill=255)
        rc = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        rc.paste(ic, (0, 0))
        rc.putalpha(mask)
        img.alpha_composite(rc, (89 + (128 - size) // 2, H - 212 + (128 - size) // 2))
    if with_text:
        d = ImageDraw.Draw(img)
        d.text((243, 258), NAME + "帮助", font=font(64), fill=(255, 255, 255, 255))
        vf = font(30)
        vw = d.textlength(VERSION, font=vf)
        d.rounded_rectangle(
            (243 + d.textlength(NAME + "帮助", font=font(64)) + 18, 262, 243 + d.textlength(NAME + "帮助", font=font(64)) + 18 + vw + 28, 262 + 46),
            radius=10,
            fill=(200, 40, 45, 255),
        )
        d.text((243 + d.textlength(NAME + "帮助", font=font(64)) + 32, 270), VERSION, font=vf, fill=(255, 255, 255, 255))
        d.text((243, 350), SUB, font=font(30), fill=(230, 230, 235, 255))
    return img.convert("RGB")


def main() -> int:
    if not SRC.exists():
        print(f"缺源图: {SRC}")
        return 1
    src = Image.open(SRC).convert("RGB")
    print(f"源图 {src.size}")

    plans = [
        ("banner_fill", fit_fill, "等比铺满+居中裁（可能切边）"),
        ("banner_pad", fit_pad, "完整放入+左右补暗色"),
        ("banner_left", fit_left, "靠左+右侧留白给标题"),
        ("banner_blur", blurred_pad, "居中+两侧自身模糊填充"),
    ]
    made = []
    for name, fn, desc in plans:
        bg = fn(src)
        out = overlay(bg)
        p = OUT_DIR / f"{name}.jpg"
        out.save(p, quality=95)
        made.append((name, desc, p))
        print(f"  {name:14s} {desc}")

    # 参考：当前默认
    if REF.exists():
        ref = overlay(Image.open(REF).convert("RGB"))
        ref.save(OUT_DIR / "banner_current.jpg", quality=95)
        print(f"  {'banner_current':14s} 当前默认（粉头发）")

    for _, _, p in made:
        print(f"\n{p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
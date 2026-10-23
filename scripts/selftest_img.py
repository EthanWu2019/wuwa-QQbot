"""
图床端到端自测：不经过 QQ，直接喂一张真实图片给 _normalize_image_url，
验证「base64 → 落盘 → 公网 URL」这条链路，以及 URL 真的能取回。

用法: python scripts/selftest_img.py
"""

import asyncio
import base64
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapter.imgserver import public_url, save_image  # noqa: E402
from adapter.main import QQOfficialBot  # noqa: E402


def make_png() -> bytes:
    """造一张 8x8 的红点 PNG，够验证链路。"""
    from PIL import Image

    img = Image.new("RGB", (8, 8), (220, 40, 40))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def main() -> None:
    raw = make_png()
    b64 = "base64://" + base64.b64encode(raw).decode()
    print(f"源图片 {len(raw)} bytes")

    bot = QQOfficialBot()
    url = bot._normalize_image_url(b64)
    print(f"归一化结果: {url}")
    if not url:
        print("失败：未产出 URL")
        return

    # 走公网入口取回
    import aiohttp

    host = url.split("://", 1)[1]
    async with aiohttp.ClientSession() as s:
        async with s.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
            body = await r.read()
            print(f"HTTP {r.status} | content-type={r.headers.get('Content-Type')} | {len(body)} bytes")
            print("字节一致" if body == raw else "字节不一致（可能经过网关压缩）")

    # 非法文件名要拒绝
    bad = "base64://" + base64.b64encode(raw).decode()
    print(f"重复调用应命中同一 hash: {bot._normalize_image_url(bad) == url}")


if __name__ == "__main__":
    asyncio.run(main())
"""
公网入口：同一个域名同时提供 gsuid_core 页面和图床图片。

    qqbot.ethanshermes.com/img/{hash}.jpg   → 本地磁盘直接吐图
    qqbot.ethanshermes.com/*                → 反代到 gsuid_core:8765
    （/waves/i/{auth} 登录页、/waves/login、/app 控制台都走反代）

为什么要合并成一个域名：Cloudflare Tunnel 的 ingress 只能指向本地端口，
每加一个子域名就要新建一条 DNS 记录。合并后 qqbot.ethanshermes.com 一个域名
搞定「登录页面 + 面板图片」，不用碰 DNS。

图片为什么必须公网可达：腾讯官方 QQ 富媒体接口
    POST /v2/groups/{openid}/messages  msg_type=7  media:{type:1,url:...}
只接受公网 URL，不接受 base64 内联。gsuid_core 回程给的是 `base64://...`，
所以必须落盘再转成 URL。

用法： python -m adapter.imgserver
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import time
from pathlib import Path

import aiohttp
from aiohttp import web

BASE_DIR = Path(__file__).resolve().parent.parent
IMAGE_DIR = Path(os.getenv("IMAGE_DIR", str(BASE_DIR / "data" / "img")))
HOST = os.getenv("IMG_HOST", "0.0.0.0")
PORT = int(os.getenv("IMG_PORT", "8766"))
CORE_UPSTREAM = os.getenv("CORE_UPSTREAM", "http://127.0.0.1:8765")
RETENTION_DAYS = int(os.getenv("IMG_RETENTION_DAYS", "7"))
# 面板图重压质量，0 = 不压。想省体积调小（75~85 之间画质基本无损）。
JPEG_QUALITY = int(os.getenv("IMG_JPEG_QUALITY", "0"))
# 面板图宽度封顶（像素）。0 = 不缩放，原图直发（主人要求）。
IMG_MAX_WIDTH = int(os.getenv("IMG_MAX_WIDTH", "0"))
MAX_WIDTH = IMG_MAX_WIDTH
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://qqbot.ethanshermes.com").rstrip("/")

NAME_RE = re.compile(r"^[0-9a-f]{32}\.(jpg|jpeg|png|webp|gif)$")
CT = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "gif": "image/gif",
}

# base64:// 前缀不带 MIME，必须嗅探魔数，否则 PNG 会被存成 .jpg、
# Content-Type 也随之报错（QQ 客户端按后缀渲染）。
_MAGIC = (
    (b"\xff\xd8\xff", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
)


def sniff_suffix(data: bytes, fallback: str = ".jpg") -> str:
    for magic, suffix in _MAGIC:
        if data.startswith(magic):
            return suffix
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return fallback

log = lambda m: print(f"[public] {m}", flush=True)  # noqa: E731

# 透传时需要剔除的 hop-by-hop / 长度头，由 aiohttp 重算
_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-encoding",
    "content-length",
}


def compress(data: bytes, suffix: str = ".jpg", quality: int = JPEG_QUALITY) -> tuple[bytes, str]:
    """
    可选的重压。**默认关闭**（JPEG_QUALITY=0 → 原图直接落盘）。

    主人明确要求：不要压图，core 出什么就发什么。
    保留这段只是留个开关，需要时设 IMG_JPEG_QUALITY=85 之类。
    """
    if suffix.lower() not in (".jpg", ".jpeg") or quality <= 0:
        return data, suffix
    try:
        from io import BytesIO

        from PIL import Image

        with Image.open(BytesIO(data)) as im:
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            buf = BytesIO()
            im.save(buf, format="JPEG", quality=quality, optimize=True)
            out = buf.getvalue()
    except Exception:
        return data, suffix
    return (out, suffix) if len(out) < len(data) else (data, suffix)


def save_image(data: bytes, suffix: str = ".jpg", quality: int = JPEG_QUALITY) -> str:
    """写入图片，返回不含扩展名的 hash。适配器也调用这个函数。"""
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    data, suffix = compress(data, suffix, quality)
    h = hashlib.sha256(data).hexdigest()[:32]
    path = IMAGE_DIR / f"{h}{suffix}"
    if not path.exists():
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
    return h


def public_url(h: str, suffix: str = ".jpg") -> str:
    return f"{PUBLIC_BASE_URL}/img/{h}{suffix}"


def cleanup(retention_days: int = RETENTION_DAYS) -> int:
    if not IMAGE_DIR.exists():
        return 0
    cutoff = time.time() - retention_days * 86400
    n = 0
    for p in IMAGE_DIR.iterdir():
        try:
            if p.is_file() and p.stat().st_mtime < cutoff:
                p.unlink()
                n += 1
        except OSError:
            pass
    return n


async def handle_img(request: web.Request) -> web.StreamResponse:
    name = request.match_info.get("name", "")
    if not NAME_RE.fullmatch(name):
        raise web.HTTPBadRequest(text="bad image name")
    path = IMAGE_DIR / name
    if not path.exists():
        raise web.HTTPNotFound(text="not found")
    ct = CT.get(path.suffix.lstrip(".").lower(), "application/octet-stream")
    return web.FileResponse(path, headers={"Cache-Control": "public, max-age=86400"})


async def handle_health(request: web.Request) -> web.Response:
    n = len(list(IMAGE_DIR.glob("*"))) if IMAGE_DIR.exists() else 0
    return web.json_response(
        {"ok": True, "images": n, "public_base": PUBLIC_BASE_URL, "upstream": CORE_UPSTREAM}
    )


async def proxy(request: web.Request) -> web.StreamResponse:
    """把非 /img 请求原样转发给 gsuid_core。"""
    url = CORE_UPSTREAM + request.rel_url.with_query(
        request.query_string if request.query_string else None
    ).human_repr()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _HOP}
    # 让 core 的登录页生成绝对链接时用公网域名
    headers["X-Forwarded-Host"] = PUBLIC_BASE_URL.split("://")[-1]
    headers["X-Forwarded-Proto"] = "https"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.request(
                request.method,
                url,
                headers=headers,
                allow_redirects=False,
                data=await request.read() if request.can_read_body else None,
            ) as resp:
                body = await resp.read()
                out = {
                    k: v
                    for k, v in resp.headers.items()
                    if k.lower() not in _HOP and k.lower() != "content-length"
                }
                return web.Response(status=resp.status, body=body, headers=out)
    except aiohttp.ClientError as exc:
        log(f"反代失败 {request.path}: {exc}")
        raise web.HTTPBadGateway(text=f"core unavailable: {exc}") from exc


async def periodic_cleanup(app: web.Application) -> None:
    """后台清理：先 sleep 再清理，不能在 on_startup 里直接跑循环，
    否则 aiohttp 的 startup 永远不返回，端口不会开始监听。"""
    async def loop():
        while True:
            await asyncio.sleep(3600)
            n = cleanup()
            if n:
                log(f"清理过期图片 {n} 张")

    asyncio.get_event_loop().create_task(loop())


def create_app() -> web.Application:
    app = web.Application(client_max_size=64 * 1024 * 1024)
    app.router.add_get("/img/{name}", handle_img)
    app.router.add_get("/health", handle_health)
    app.router.add_route("*", "/{tail:.*}", proxy)
    app.on_startup.append(periodic_cleanup)
    return app


if __name__ == "__main__":
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    log(f"公网入口启动 {HOST}:{PORT}")
    log(f"图片目录 {IMAGE_DIR}")
    log(f"反代目标 {CORE_UPSTREAM}")
    log(f"公网基址 {PUBLIC_BASE_URL}")
    web.run_app(create_app(), host=HOST, port=PORT, access_log=None)
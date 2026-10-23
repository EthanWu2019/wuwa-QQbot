"""
QQ 官方机器人 → gsuid_core 适配器

架构（gsuid_core 是插件宿主，不直连聊天平台）：
    QQ 官方 API (WebSocket)
        │  op10 Hello → op2 Identify → op0 Dispatch(收消息)
        │  op1 心跳
        ▼
    本适配器
        │  ws://core:8765/ws/qq  (msgpack 双向)
        │  ── MessageReceive  ──▶  gsuid_core（跑鸣潮插件，出图片）
        │  ◀── MessageSend    ──   gsuid_core
        ▼
    QQ 官方 REST API (发消息 / 上传富媒体)

只做一件事：把鸣潮插件的输出按 QQ 开发者文档合规地发出去。没有 AI 对话。

鉴权：Bearer 用 `QQBot <access_token>` 前缀（不是裸 token）。
参考：https://bot.q.qq.com/wiki
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import ssl
import time
from pathlib import Path
from typing import Any, Optional

import aiohttp
import msgspec

log = logging.getLogger("qq_official_adapter")

# ── 配置 ──────────────────────────────────────────────────────────────
APP_ID = os.getenv("QQ_APP_ID", "").strip()
APP_SECRET = os.getenv("QQ_APP_SECRET", "").strip()  # 注意：官方叫 AppSecret，核心变量名是 CLIENT_SECRET
TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
API_BASE = os.getenv("QQ_API_BASE", "https://api.sgroup.qq.com")

CORE_WS_URL = os.getenv("CORE_WS_URL", "ws://127.0.0.1:8765/ws/qq").strip()
CORE_WS_TOKEN = os.getenv("CORE_WS_TOKEN", "").strip()
BOT_ID = os.getenv("GSUID_BOT_ID", "qq").strip()
SELF_ID = os.getenv("QQ_BOT_SELF_ID", "").strip()  # AppID 即 bot 自身 openid 侧的 uid

# Intents: 群/C2C 事件(1<<25) + @消息(1<<30) + 频道私信(1<<12) + 群成员(1<<26)
INTENTS = (1 << 25) | (1 << 30) | (1 << 12) | (1 << 26)

RECV_HEARTBEAT_ACK = False
_ws_seq: Optional[int] = None
_session_id: Optional[str] = None


# ── 鉴权 ──────────────────────────────────────────────────────────────
class TokenManager:
    """access_token 缓存，官方有效期 7200s，提前 5 分钟刷新。"""

    def __init__(self) -> None:
        self._token: str = ""
        self._expire_at: float = 0.0
        self._lock = asyncio.Lock()

    async def get(self, session: aiohttp.ClientSession) -> str:
        async with self._lock:
            if self._token and time.time() < self._expire_at - 300:
                return self._token
            payload = {"appId": APP_ID, "clientSecret": APP_SECRET}
            async with session.post(TOKEN_URL, json=payload) as resp:
                data = await resp.json()
            token = data.get("access_token")
            if not token:
                raise RuntimeError(f"获取 access_token 失败: {data}")
            self._token = token
            self._expire_at = time.time() + float(data.get("expires_in", 7200))
            log.info("access_token 已刷新，有效期 %s 秒", data.get("expires_in"))
            return token

    @property
    def header(self) -> str:
        return f"QQBot {self._token}"


token_mgr = TokenManager()


def auth_headers(token: str, content_type: bool = True) -> dict[str, str]:
    h = {"Authorization": f"QQBot {token}"}
    if content_type:
        h["Content-Type"] = "application/json"
    return h


# ── gsuid_core WS 客户端 ──────────────────────────────────────────────
class CoreClient:
    """维护到 gsuid_core 的 msgpack WS 连接，收 MessageSend → 发到 QQ。"""

    def __init__(self, on_send) -> None:
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._on_send = on_send
        self._task: Optional[asyncio.Task] = None
        self._connected = asyncio.Event()

    @property
    def connected(self) -> bool:
        return self._ws is not None and not self._ws.closed

    async def _run(self) -> None:
        backoff = 2
        while True:
            try:
                url = CORE_WS_URL
                if CORE_WS_TOKEN:
                    sep = "&" if "?" in url else "?"
                    url = f"{url}{sep}token={CORE_WS_TOKEN}"
                async with aiohttp.ClientSession() as s:
                    async with s.ws_connect(url, heartbeat=30, max_msg_size=0) as ws:
                        self._ws = ws
                        self._connected.set()
                        log.info("已连上 gsuid_core: %s", CORE_WS_URL)
                        backoff = 2
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.BINARY:
                                await self._handle(msg.data)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("gsuid_core WS 断开(%s)，%ss 后重连", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    async def _handle(self, data: bytes) -> None:
        try:
            frame = msgspec.json.decode(data)  # 占位，下面按实际格式覆盖
        except Exception:
            frame = None
        try:
            import msgspec.msgpack as mp

            frame = mp.decode(data)
        except Exception as exc:
            log.warning("解码 MessageSend 失败: %s", exc)
            return
        await self._on_send(frame)

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def send(self, payload: dict[str, Any]) -> None:
        if not self.connected:
            log.warning("core 未连接，丢弃一条消息")
            return
        import msgspec.msgpack as mp

        await self._ws.send_bytes(mp.encode(payload))


# ── QQ 官方 API 发消息 ─────────────────────────────────────────────────
def _clean_text(text: str) -> str:
    """官方 QQ 文本消息会渲染 @，裸 @ 需转义为全角或去掉。"""
    # 去掉 qq 提及标记残留
    text = re.sub(r"<@!?\d+>", "", text)
    return text.strip()


async def upload_rich_media(
    session: aiohttp.ClientSession,
    token: str,
    file_bytes: bytes,
    file_name: str,
    srv_send_msg: bool = False,
) -> Optional[str]:
    """
    富媒体上传，返回 file_info（发 msg_type=7 时用）。
    官方要求先 POST /v2/groups/{openid}/files 或 /v2/users/{openid}/files
    """
    url = f"{API_BASE}/v2/files"
    payload = {
        "file_type": 1,  # 1=图片
        "url": "",
        "srv_send_msg": srv_send_msg,
        "file_data": base64.b64encode(file_bytes).decode(),
        "file_name": file_name,
    }
    async with session.post(
        url, headers=auth_headers(token, content_type=False), json=payload
    ) as resp:
        data = await resp.json()
    return data.get("file_info")


async def send_group_text(
    session: aiohttp.ClientSession, token: str, group_openid: str, content: str, msg_id: str
) -> dict:
    url = f"{API_BASE}/v2/groups/{group_openid}/messages"
    payload = {"content": _clean_text(content), "msg_type": 0, "msg_id": msg_id}
    async with session.post(url, headers=auth_headers(token), json=payload) as resp:
        return await resp.json()


async def send_group_image_by_url(
    session: aiohttp.ClientSession, token: str, group_openid: str, url: str, msg_id: str
) -> dict:
    """
    用公网 URL 发图。官方 base 64.9 万字节上限内可行，但要求 URL 公网可达。
    """
    endpoint = f"{API_BASE}/v2/groups/{group_openid}/messages"
    payload = {
        "content": "",
        "msg_type": 7,
        "msg_id": msg_id,
        "media": {"type": 1, "url": url},
    }
    async with session.post(endpoint, headers=auth_headers(token), json=payload) as resp:
        return await resp.json()


async def send_c2c_image_by_url(
    session: aiohttp.ClientSession, token: str, openid: str, url: str, msg_id: str
) -> dict:
    endpoint = f"{API_BASE}/v2/users/{openid}/messages"
    payload = {
        "content": "",
        "msg_type": 7,
        "msg_id": msg_id,
        "media": {"type": 1, "url": url},
    }
    async with session.post(endpoint, headers=auth_headers(token), json=payload) as resp:
        return await resp.json()


def _to_text(content: list[dict[str, Any]]) -> str:
    out: list[str] = []
    for seg in content or []:
        t = seg.get("type")
        d = seg.get("data")
        if t == "text":
            out.append(str(d))
        elif t == "image":
            out.append("[图片]")
    return "\n".join(out).strip()


def _extract_images(content: list[dict[str, Any]]) -> list[str]:
    urls: list[str] = []
    for seg in content or []:
        if seg.get("type") == "image":
            d = seg.get("data")
            if isinstance(d, str) and d:
                urls.append(d)
            elif isinstance(d, dict):
                for k in ("url", "file", "path"):
                    if d.get(k):
                        urls.append(str(d[k]))
                        break
    return urls
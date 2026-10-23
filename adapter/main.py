"""
适配器主程序：QQ 官方网关 ⇄ gsuid_core

用法：
    python -m adapter.main      # 在 gsuid_core 已启动的前提下运行
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapter.qq_official_adapter import (  # noqa: E402
    API_BASE,
    APP_ID,
    APP_SECRET,
    BOT_ID,
    CORE_WS_TOKEN,
    INTENTS,
    SELF_ID,
    CoreClient,
    auth_headers,
    send_c2c_image_by_url,
    send_group_image_by_url,
    send_group_text,
    token_mgr,
    _extract_images,
    _to_text,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("qqbot.main")


class QQOfficialBot:
    def __init__(self) -> None:
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.seq: Optional[int] = None
        self.session_id: Optional[str] = None
        self.core: Optional[CoreClient] = None
        # msg_id 必须随被动回复一起回传，官方群/C2C 只能被动回复
        self._recent_msg_ids: dict[str, str] = {}
        self._heartbeat_task: Optional[asyncio.Task] = None
        # 登录页公网地址：鸣潮插件生成链接时用它
        self.public_base = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

    async def get_gateway_url(self, token: str) -> str:
        async with self.session.get(
            f"{API_BASE}/gateway", headers=auth_headers(token, content_type=False)
        ) as resp:
            data = await resp.json()
            return data["url"]

    async def run(self) -> None:
        conn = aiohttp.TCPConnector(ssl=ssl_ctx())
        self.session = aiohttp.ClientSession(connector=conn)
        self.core = CoreClient(self._on_core_send)
        await self.core.start()

        backoff = 2
        while True:
            try:
                token = await token_mgr.get(self.session)
                gw_url = await self.get_gateway_url(token)
                log.info("网关地址: %s", gw_url)
                async with self.session.ws_connect(
                    gw_url, heartbeat=None, max_msg_size=0
                ) as ws:
                    self.ws = ws
                    backoff = 2
                    await self._read_loop(ws, token)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("QQ 网关断开(%s)，%ss 后重连", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def _read_loop(self, ws: aiohttp.ClientWebSocketResponse, token: str) -> None:
        async for msg in ws:
            if msg.type != aiohttp.WSMsgType.TEXT:
                continue
            payload = json.loads(msg.data)
            op = payload.get("op")
            if payload.get("s") is not None:
                self.seq = payload["s"]

            if op == 10:  # Hello
                interval = payload["d"]["heartbeat_interval"] / 1000.0
                await ws.send_json(
                    {
                        "op": 2,
                        "d": {
                            "token": f"QQBot {token}",
                            "intents": INTENTS,
                            "shard": [0, 1],
                        },
                    }
                )
                self._heartbeat_task = asyncio.create_task(self._heartbeat(ws, interval))
            elif op == 0:
                await self._dispatch(payload.get("t", ""), payload.get("d", {}))
            elif op == 7:
                log.info("服务端要求重连 (op 7)")
                await ws.close()

    async def _heartbeat(self, ws: aiohttp.ClientWebSocketResponse, interval: float) -> None:
        while True:
            await asyncio.sleep(interval)
            try:
                await ws.send_json({"op": 1, "d": self.seq})
            except Exception:
                return

    async def _dispatch(self, event: str, data: dict[str, Any]) -> None:
        log.info("收到事件 %s", event)
        if event in ("GROUP_AT_MESSAGE_CREATE", "AT_MESSAGE_CREATE"):
            await self._on_group_message(data)
        elif event == "C2C_MESSAGE_CREATE":
            await self._on_c2c_message(data)

    async def _on_group_message(self, data: dict[str, Any]) -> None:
        group_openid = data.get("group_openid", "")
        user = data.get("author", {}) or {}
        user_openid = user.get("user_openid", "")
        user_id = user.get("id") or user_openid
        msg_id = data.get("id", "")
        raw = data.get("content", "") or ""

        self._recent_msg_ids[f"g:{group_openid}"] = msg_id
        await self._forward_core(
            bot_id=BOT_ID,
            user_type="group",
            group_id=group_openid,
            user_id=user_id,
            msg_id=msg_id,
            raw_text=raw,
            target_kind="group",
        )

    async def _on_c2c_message(self, data: dict[str, Any]) -> None:
        user = data.get("author", {}) or {}
        user_openid = user.get("user_openid", "")
        msg_id = data.get("id", "")
        raw = data.get("content", "") or ""

        self._recent_msg_ids[f"c:{user_openid}"] = msg_id
        await self._forward_core(
            bot_id=BOT_ID,
            user_type="direct",
            group_id=None,
            user_id=user_openid or user.get("id", ""),
            msg_id=msg_id,
            raw_text=raw,
            target_kind="c2c",
        )

    async def _forward_core(
        self,
        *,
        bot_id: str,
        user_type: str,
        group_id: Optional[str],
        user_id: str,
        msg_id: str,
        raw_text: str,
        target_kind: str,
    ) -> None:
        """把 QQ 消息转成 MessageReceive 帧推给 gsuid_core。"""
        frame = {
            "bot_id": bot_id,
            "bot_self_id": SELF_ID or APP_ID,
            "msg_id": msg_id,
            "user_type": user_type,
            "group_id": group_id,
            "user_id": user_id,
            "sender": {"nickname": "", "user_id": user_id},
            "content": [{"type": "text", "data": raw_text}],
            # 内部标记：回程时用来决定发群还是私聊
            "_reply_target": target_kind,
        }
        # 附加字段放在顶层，core 的 Struct 允许未知字段忽略
        if self.core:
            await self.core.send(frame)

    async def _on_core_send(self, frame: dict[str, Any]) -> None:
        """收到 gsuid_core 的 MessageSend → 按官方文档发到 QQ。"""
        content = frame.get("content") or []
        target_type = frame.get("target_type")
        target_id = frame.get("target_id") or frame.get("group_id")
        msg_id = frame.get("msg_id") or ""

        text = _to_text(content)
        images = _extract_images(content)

        token = await token_mgr.get(self.session)

        # 1) 图片优先（鸣潮面板都是图）
        for img in images:
            url = self._normalize_image_url(img)
            if not url:
                continue
            try:
                if target_type == "direct":
                    res = await send_c2c_image_by_url(
                        self.session, token, target_id, url, msg_id
                    )
                else:
                    res = await send_group_image_by_url(
                        self.session, token, target_id, url, msg_id
                    )
                log.info("发图 %s -> %s", url[:80], res.get("id", res))
            except Exception as exc:
                log.warning("发图失败: %s", exc)

        # 2) 文本
        if text:
            if target_type == "direct":
                # C2C 文本
                url = f"{API_BASE}/v2/users/{target_id}/messages"
                payload = {"content": text, "msg_type": 0, "msg_id": msg_id}
                async with self.session.post(
                    url, headers=auth_headers(token), json=payload
                ) as resp:
                    res = await resp.json()
                log.info("发私聊文本 -> %s", res.get("id", res))
            else:
                res = await send_group_text(self.session, token, target_id, text, msg_id)
                log.info("发群文本 -> %s", res.get("id", res))

    def _normalize_image_url(self, val: str) -> str:
        """
        gsuid_core 可能给 base64 / 本地路径 / 公网 URL。
        官方 API 只接受公网可达 URL，本地路径需要我们自建图床。
        """
        if val.startswith("http://") or val.startswith("https://"):
            return val
        if val.startswith("data:"):
            b64 = val.split(",", 1)[1]
            return f"{self.public_base}/img/{b64[:32]}"  # 占位，见 README
        return ""


def ssl_ctx():
    import ssl as _ssl

    ctx = _ssl.create_default_context()
    return ctx


async def main() -> None:
    if not APP_ID or not APP_SECRET:
        log.error("缺少 QQ_APP_ID / QQ_APP_SECRET")
        sys.exit(1)
    bot = QQOfficialBot()
    log.info("适配器启动，AppID=%s，核心=%s", APP_ID, os.getenv("CORE_WS_URL"))
    await bot.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
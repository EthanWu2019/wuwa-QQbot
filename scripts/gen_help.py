"""生成一张帮助图到本地，用来肉眼看 branding 有没有生效。

用法：.venv/bin/python scripts/gen_help.py [命令]
输出：data/preview.jpg
"""

import asyncio
import base64
import pathlib
import sys

import aiohttp
import msgspec.json as msgjson
from gsuid_core.models import Message, MessageReceive

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "vendor" / "gsuid_core"))

OUT = ROOT / "data" / "preview.jpg"
CMD = sys.argv[1] if len(sys.argv) > 1 else "ww帮助"


def decode_b64(data: str) -> bytes:
    """core 回程 `base64://<payload>`，payload 可能缺 padding。"""
    payload = data.split("base64://", 1)[1]
    payload += "=" * (-len(payload) % 4)
    return base64.b64decode(payload)


async def main(text: str) -> None:
    async with aiohttp.ClientSession() as s:
        async with s.ws_connect("ws://127.0.0.1:8765/ws/qq", max_msg_size=0) as ws:
            r = MessageReceive(
                bot_id="qq",
                bot_self_id="1905904359",
                msg_id="preview-1",
                user_type="direct",
                group_id=None,
                user_id="3401895383",
                sender={"nickname": "preview"},
                content=[Message(type="text", data=text)],
            )
            await ws.send_bytes(msgjson.encode(r))
            print(f"已发送: {text}")
            async with asyncio.timeout(90):
                async for m in ws:
                    if m.type != aiohttp.WSMsgType.BINARY:
                        continue
                    out = msgjson.decode(m.data)
                    for seg in out.get("content") or []:
                        data = str(seg.get("data", ""))
                        if seg.get("type") == "image" and "base64://" in data:
                            raw = decode_b64(data)
                            OUT.parent.mkdir(parents=True, exist_ok=True)
                            OUT.write_bytes(raw)
                            print(f"图片 {len(raw) // 1024}KB -> {OUT}")
                            return
                        if seg.get("type") == "text":
                            print("文本:", data[:200])
                    return
    print("无图片回程")


if __name__ == "__main__":
    asyncio.run(main(CMD))
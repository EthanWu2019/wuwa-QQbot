"""
链路自测：不经过 QQ，直接往 core 的 WS 塞一条 MessageReceive，
看鸣潮插件是否产生 MessageSend 回程。用来区分「适配器问题」还是「core/插件问题」。

用法: python scripts/selftest_core.py "鸣潮帮助"
"""

import asyncio
import sys

import msgspec.json as msgjson

CORE = "ws://127.0.0.1:8765/ws/qq"


async def main(text: str) -> None:
    import aiohttp

    async with aiohttp.ClientSession() as s:
        async with s.ws_connect(CORE, max_msg_size=0) as ws:
            frame = {
                "bot_id": "qq",
                "bot_self_id": "1905904359",
                "msg_id": "selftest-1",
                "user_type": "direct",
                "group_id": None,
                "user_id": "3401895383",
                "sender": {"nickname": "selftest"},
                "content": [{"type": "text", "data": text}],
            }
            await ws.send_bytes(msgjson.encode(frame))
            print(f"已注入: {text}")
            try:
                async with asyncio.timeout(60):
                    while True:
                        msg = await ws.receive()
                        if msg.type == aiohttp.WSMsgType.BINARY:
                            out = msgjson.decode(msg.data)
                            kinds = [
                                (s.get("type"), str(s.get("data"))[:120])
                                for s in (out.get("content") or [])
                            ]
                            print("收到回程 ->", out.get("target_type"), kinds)
                        elif msg.type in (
                            aiohttp.WSMsgType.CLOSE,
                            aiohttp.WSMsgType.CLOSED,
                            aiohttp.WSMsgType.CLOSING,
                        ):
                            print("连接关闭")
                            return
            except asyncio.TimeoutError:
                print("40s 内无回程")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "鸣潮帮助"))
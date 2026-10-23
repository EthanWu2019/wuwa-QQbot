"""
诊断探针：在 core 进程外模拟一次命令匹配，定位「事件收到但无服务响应」。

连接 WS 发一条消息，同时把 core 的公开日志级别调到 TRACE 前的静态检查：
- 直接 import 插件，注册到本进程，然后跑 trigger index 匹配。
这能区分「插件/触发器本身有问题」与「core 运行时环境问题」。
"""

import asyncio
import sys

import msgspec.json as msgjson


async def main(text: str) -> None:
    import aiohttp
    from gsuid_core.models import Message, MessageReceive

    async with aiohttp.ClientSession() as s:
        async with s.ws_connect("ws://127.0.0.1:8765/ws/qq", max_msg_size=0) as ws:
            r = MessageReceive(
                bot_id="qq",
                bot_self_id="1905904359",
                msg_id="probe-1",
                user_type="direct",
                group_id=None,
                user_id="3401895383",
                sender={"nickname": "probe"},
                content=[Message(type="text", data=text)],
            )
            await ws.send_bytes(msgjson.encode(r))
            print(f"已发送: {text}")
            try:
                async with asyncio.timeout(75):
                    async for m in ws:
                        if m.type == aiohttp.WSMsgType.BINARY:
                            out = msgjson.decode(m.data)
                            segs = [
                                (x.get("type"), str(x.get("data"))[:100])
                                for x in (out.get("content") or [])
                            ]
                            print("回程:", out.get("target_type"), segs)
                            return
                        if m.type in (
                            aiohttp.WSMsgType.CLOSE,
                            aiohttp.WSMsgType.CLOSED,
                            aiohttp.WSMsgType.CLOSING,
                            aiohttp.WSMsgType.ERROR,
                        ):
                            print("连接关闭:", m.type)
                            return
            except asyncio.TimeoutError:
                print("75s 无回程")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "帮助"))
"""
测试 QQ 富媒体消息的 content 字段：
  A) content=" "     （当前实现）
  B) content=""      （空字符串）
  C) 不带 content 字段（按官方文档）

用法：.venv/bin/python scripts/test_media_content.py
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "adapter"))

import aiohttp

from qq_official_adapter import API_BASE, auth_headers, next_msg_seq


def load_env() -> None:
    env = Path(__file__).resolve().parent.parent / ".env"
    for line in env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


OWNER = "5E7C8B8BDDEB7F263662B0E3A3BF3A85"


async def get_token(session: aiohttp.ClientSession) -> str:
    payload = {
        "appId": os.environ["QQ_APP_ID"],
        "clientSecret": os.environ["QQ_APP_SECRET"],
    }
    async with session.post(
        "https://bots.qq.com/app/getAppAccessToken", json=payload
    ) as resp:
        data = await resp.json()
    return data["access_token"]


async def upload(session, token: str, url: str) -> str:
    payload = {"file_type": 1, "url": url}
    async with session.post(
        f"{API_BASE}/v2/users/{OWNER}/files",
        headers=auth_headers(token),
        json=payload,
    ) as resp:
        data = await resp.json()
    return data.get("file_info") or (data.get("data") or {}).get("file_info") or ""


async def send(session, token: str, file_info: str, variant: str) -> dict:
    payload: dict = {
        "msg_type": 7,
        "msg_id": "",
        "msg_seq": next_msg_seq(f"users:{OWNER}"),
        "media": {"file_info": file_info},
    }
    if variant == "space":
        payload["content"] = " "
    elif variant == "empty":
        payload["content"] = ""

    async with session.post(
        f"{API_BASE}/v2/users/{OWNER}/messages",
        headers=auth_headers(token),
        json=payload,
    ) as resp:
        return await resp.json()


async def main() -> None:
    load_env()
    img_url = sys.argv[1] if len(sys.argv) > 1 else ""
    if not img_url:
        print("用法: test_media_content.py <公网图片URL>")
        return

    async with aiohttp.ClientSession() as session:
        token = await get_token(session)
        file_info = await upload(session, token, img_url)
        if not file_info:
            print("❌ 上传失败")
            return
        print(f"✓ 拿到 file_info: {file_info[:40]}...")

        for variant in ("space", "empty", "none"):
            res = await send(session, token, file_info, variant)
            ok = res.get("id")
            print(f"  [{variant:5}] {'✅ 成功' if ok else '❌ 失败'} {ok or res}")
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())

# wuwa-QQbot

鸣潮插件（WutheringWavesUID）驱动的 **QQ 官方机器人**。只做鸣潮一件事，没有 AI 对话。

## 架构

```
QQ 官方开放平台（api.sgroup.qq.com）
   │  WebSocket：op10 Hello → op2 Identify → op1 心跳 → op0 Dispatch
   ▼
adapter/  ← 本仓库写的适配器
   │  msgpack 双向帧：MessageReceive → core ／ MessageSend ← core
   ▼
gsuid_core 0.11.2（早柚核心，8765）
   │  内置 Web 面板 + 数据库
   ▼
XutheringWavesUID 插件（鸣潮，104 服务 / 116 触发器 / 111 帮助命令）
```

gsuid_core 是**插件宿主**，自己不直连聊天平台，所以官方 bot 的接入由本仓库的
`adapter/` 负责。这一层是本项目存在的唯一理由。

## 为什么用 gsuid_core 而不是剥离

插件对 `gsuid_core` 有 431 处引用，横跨 26 个子模块，且 `gsuid_core.bot.Bot` /
`gsuid_core.models.Event` / `gsuid_core.segment.MessageSegment` 贯穿所有功能模块的
方法签名。剥离等于重写整个插件。核心本体是开源的（GPL-3.0），但作为宿主使用
才是它的设计意图。

## 目录

```
adapter/qq_official_adapter.py   鉴权、token 缓存、core WS 客户端、发消息封装
adapter/main.py                  QQ 网关主循环 + 事件分发 + 回程发送
scripts/run_core.sh              启动 gsuid_core
scripts/run_adapter.sh           启动适配器（读 .env）
vendor/gsuid_core/               核心源码（gitignored，可重新 clone）
```

## 快速开始

```bash
python3.12 -m venv .venv
.venv/bin/pip install ./vendor/gsuid_core
.venv/bin/pip install -e /path/to/XutheringWavesUID
ln -sfn /path/to/XutheringWavesUID vendor/gsuid_core/gsuid_core/plugins/XutheringWavesUID

./scripts/run_core.sh      # 终端 1：监听 8765
./scripts/run_adapter.sh   # 终端 2：连 QQ 网关 + core
```

首次启动会从 `ww2.loping151.top` 下载约 100MB 插件资源。

## 配置（.env，chmod 600，不入 git）

| 变量 | 说明 |
|---|---|
| `QQ_APP_ID` / `QQ_APP_SECRET` | 开放平台凭证 |
| `CORE_WS_URL` | `ws://127.0.0.1:8765/ws/qq` |
| `GSUID_BOT_ID` | `qq` |
| `PUBLIC_BASE_URL` | 公网登录域名，如 `https://qqbot.ethanshermes.com` |

## 官方 API 要点（合规）

- 鉴权头是 `Authorization: QQBot <token>`，**不是**裸 token
- access_token 有效期 7200s，提前 5 分钟刷新
- 群/C2C **只能被动回复**，必须带 `msg_id`，不支持主动推送
- 群消息 `POST /v2/groups/{openid}/messages`，C2C `POST /v2/users/{openid}/messages`
- 富媒体 `msg_type=7` + `media:{type:1,url:...}`，**URL 必须公网可达**
- Intents：`(1<<25)群/C2C | (1<<30)@消息 | (1<<12)频道私信 | (1<<26)群成员`

## 待办

- [ ] Cloudflare Tunnel：`qqbot.ethanshermes.com` → 127.0.0.1:8765
- [ ] 登录链接公网化：core 配置 `WavesLoginUrl` = `https://qqbot.ethanshermes.com`
- [ ] 图片发送：core 产出本地图片/base64，需自建图床转公网 URL
- [ ] launchd 常驻 + 日志轮转

## 致谢

- [Genshin-bots/gsuid_core](https://github.com/Genshin-bots/gsuid_core) — GPL-3.0
- [Loping151/XutheringWavesUID](https://github.com/Loping151/XutheringWavesUID) — GPL-3.0
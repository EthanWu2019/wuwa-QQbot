"""泰缇斯系统 - 帮助界面品牌信息。

owner 自定义版本号与文案。插件更新会覆盖 get_help.py 等文件，
所以统一从这里取，改版只动这一个文件。

版本规则（主人 2026-10-23 定）：
  1.0.0  首个正式版（插件本体 + 图床/公网 + 签到等四插件 + launchd）
  1.0.1  后续小修补丁递增，破坏性改动进第二位，重大功能进第一位
"""

# 机器人显示名（原：XutheringWavesUID）
BOT_NAME = "泰缇斯系统"

# 版本号（原：3.7.1，跟着上游走没意义）
BOT_VERSION = "1.0.0"

# banner 副标题（原："漂泊者，欢迎在这个时代醒来。"）
BANNER_SUB_TEXT = "这里是黑海岸，你永远的家。"

# 需要同步改 plugin_name 的帮助页清单
#   wutheringwaves_help/get_help.py     → ww帮助
#   wutheringwaves_help/change_help.py  → ww替换帮助
#   wutheringwaves_weight/weight_help.py → ww权重帮助
HELP_PAGES = (
    "wutheringwaves_help/get_help.py",
    "wutheringwaves_help/change_help.py",
    "wutheringwaves_weight/weight_help.py",
)
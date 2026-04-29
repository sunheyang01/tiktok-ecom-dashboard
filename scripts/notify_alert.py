"""向飞书群发送告警消息

用法:
    python3 notify_alert.py "标题" "正文行1" "正文行2" ...
    或: echo "正文" | python3 notify_alert.py "标题"

依赖与 analyze.py 相同的 FEISHU_BOT_APP_ID / FEISHU_BOT_APP_SECRET / FEISHU_CHAT_ID。
"""
import os
import sys

from feishu_client import FeishuClient

CHAT_ID = os.environ.get("FEISHU_CHAT_ID", "oc_c4c7c8a6c2ebaf0a7f563d15a5327f6f")
BOT_APP_ID = os.environ.get("FEISHU_BOT_APP_ID", "cli_a94c27d2af38dbb5")
BOT_APP_SECRET = os.environ.get("FEISHU_BOT_APP_SECRET", "KZzghjmQbtdVl2fWoR5febQmBxtaxyQM")


def main():
    if len(sys.argv) < 2:
        print("用法: notify_alert.py <标题> [正文行...]", file=sys.stderr)
        sys.exit(2)

    title = sys.argv[1]
    if len(sys.argv) > 2:
        body_lines = list(sys.argv[2:])
    else:
        body_lines = [line.rstrip("\n") for line in sys.stdin if line.strip()]
        if not body_lines:
            body_lines = ["（无详细信息）"]

    if not CHAT_ID:
        print("[跳过] 未配置 FEISHU_CHAT_ID")
        return

    bot = FeishuClient(app_id=BOT_APP_ID, app_secret=BOT_APP_SECRET)
    bot.send_message(CHAT_ID, title, body_lines)
    print("[完成] 飞书告警已发送")


if __name__ == "__main__":
    main()

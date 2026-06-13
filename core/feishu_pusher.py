import json
from datetime import datetime

import requests

from config import Config


class FeishuPusher:
    def __init__(self):
        self.webhook_url = Config.FEISHU_WEBHOOK_URL

    def push_news(self, news: list):
        if not self.webhook_url:
            print("  [飞书] 未配置 Webhook URL，跳过推送")
            return
        if not news:
            print("  [飞书] 无新闻可推送")
            return

        now = datetime.now().strftime("%H:%M")

        items = []
        for item in news[:10]:
            title = item["title"]
            source = item["source_name"]
            url = item.get("url", "")
            text = f"【{source}】{title}"
            if url:
                text += f"\n{url}"
            items.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": text},
            })

        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"新闻推送 ({now})"},
                "template": "green",
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": f"共 {len(news)} 条新新闻，以下为前 10 条："}},
                {"tag": "hr"},
            ] + items + [
                {"tag": "hr"},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": "A股情报系统"}]},
            ],
        }

        payload = {"msg_type": "interactive", "card": card}
        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=10)
            result = resp.json()
            if result.get("StatusCode") == 0 or result.get("code") == 0:
                print(f"  [飞书] 推送成功 ({len(news)} 条)")
            else:
                print(f"  [飞书] 推送失败: {result}")
        except Exception as e:
            print(f"  [飞书] 推送异常: {e}")

    def push_report(self, content: str):
        if not self.webhook_url or not content:
            return

        content_preview = content[:500] if content else ""
        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"简报 ({datetime.now().strftime('%H:%M')})"},
                "template": "blue",
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": content_preview}},
                {"tag": "hr"},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": "A股情报系统"}]},
            ],
        }
        payload = {"msg_type": "interactive", "card": card}
        try:
            requests.post(self.webhook_url, json=payload, timeout=10)
            print(f"  [飞书] 简报推送成功")
        except Exception as e:
            print(f"  [飞书] 简报推送异常: {e}")

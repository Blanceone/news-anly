import json
from datetime import datetime

import requests

from config import Config


class FeishuPusher:
    def __init__(self):
        self.webhook_url = Config.FEISHU_WEBHOOK_URL

    def push_news(self, news: list, report_type: str = "intraday"):
        if not self.webhook_url:
            print("  [飞书] 未配置 Webhook URL，跳过推送")
            return
        if not news:
            print("  [飞书] 无新闻可推送")
            return

        type_labels = {"pre_market": "盘前必读", "intraday": "盘中快讯", "post_market": "盘后复盘"}
        type_label = type_labels.get(report_type, "新闻推送")
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
                "title": {"tag": "plain_text", "content": f"{type_label} ({now})"},
                "template": "blue" if report_type == "pre_market" else ("indigo" if report_type == "post_market" else "green"),
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": f"共 {len(news)} 条新闻，以下为前 10 条："}},
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

    def push_report(self, report_type: str, title: str, content: str, web_url: str = ""):
        if not self.webhook_url:
            return
        type_labels = {"pre_market": "盘前必读", "intraday": "盘中快讯", "post_market": "盘后复盘"}
        type_label = type_labels.get(report_type, "报告")

        content_preview = content[:500] if content else ""
        elements = [
            {"tag": "div", "text": {"tag": "lark_md", "content": content_preview}},
        ]
        if web_url:
            elements.append({
                "tag": "action",
                "actions": [{
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "查看完整报告"},
                    "type": "primary",
                    "multi_url": {"url": web_url, "android_url": web_url, "ios_url": web_url},
                }],
            })

        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"{type_label} - {title}"},
                "template": "blue" if report_type == "pre_market" else ("indigo" if report_type == "post_market" else "green"),
            },
            "elements": elements + [
                {"tag": "hr"},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": "A股情报系统"}]},
            ],
        }
        payload = {"msg_type": "interactive", "card": card}
        try:
            requests.post(self.webhook_url, json=payload, timeout=10)
            print(f"  [飞书] 报告推送成功")
        except Exception as e:
            print(f"  [飞书] 报告推送异常: {e}")

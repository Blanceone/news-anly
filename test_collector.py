"""快速测试采集器"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import time
import requests
from config import Config

for source_id, config in Config.NEWS_SOURCES.items():
    print(f"\n[{config['name']}] 测试中...")
    api_url = config.get("api_url") or config.get("rss_url")
    if not api_url:
        print(f"  跳过: 无 URL")
        continue
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": config.get("url", ""),
    }
    try:
        resp = requests.get(api_url, headers=headers, timeout=10)
        print(f"  状态: {resp.status_code}, 大小: {len(resp.content)} bytes")
        data = resp.json()
        if source_id == "sina":
            items = data.get("result", {}).get("data", [])
            print(f"  新闻数: {len(items)}")
            for item in items[:2]:
                print(f"    - {item.get('title', '')[:50]}")
        elif source_id == "wallstreetcn":
            items = data.get("data", {}).get("items", [])
            print(f"  新闻数: {len(items)}")
            for item in items[:2]:
                print(f"    - {item.get('title', '')[:50] or item.get('content_text', '')[:50]}")
        elif source_id == "xueqiu":
            items = data.get("list", [])
            print(f"  新闻数: {len(items)}")
            for item in items[:2]:
                print(f"    - {item.get('title', '')[:50]}")
        elif source_id == "cls":
            items = data.get("data", {}).get("roll_list", [])
            print(f"  新闻数: {len(items)}")
            for item in items[:2]:
                title = item.get('title', '') or item.get('content', '')[:50]
                print(f"    - {title[:50]}")
        else:
            print(f"  响应预览: {str(data)[:100]}")
    except Exception as e:
        print(f"  失败: {type(e).__name__}: {e}")
    time.sleep(1)

print("\n=== 测试完成 ===")

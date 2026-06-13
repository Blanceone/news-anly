"""财联社 (cls.cn) 实时快讯采集"""
import hashlib
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup


def collect(config: dict, since: datetime = None) -> list:
    api_url = config["api_url"]
    params = config.get("params", {}).copy()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": config.get("url", ""),
    }
    custom_headers = config.get("headers", {})
    headers.update(custom_headers)

    params["last_time"] = str(int(time.time()))
    input_str = "&".join(f"{k}={params[k]}" for k in sorted(params))
    sign = hashlib.md5(hashlib.sha1(input_str.encode()).hexdigest().encode()).hexdigest()
    params["sign"] = sign

    resp = requests.get(api_url, params=params, headers=headers, timeout=15)
    resp.encoding = "utf-8"
    data = resp.json()

    items = []
    since_ts = since.timestamp() if since else 0
    for item in data.get("data", {}).get("roll_data", []):
        ctime = item.get("ctime", 0)
        if since and ctime <= since_ts:
            continue
        title = item.get("title", "") or BeautifulSoup(item.get("content", ""), "html.parser").get_text()[:80]
        items.append({
            "title": title,
            "content": BeautifulSoup(item.get("content", ""), "html.parser").get_text(),
            "url": f"https://www.cls.cn/detail/{item.get('id')}",
            "source": "cls",
            "source_name": "财联社",
            "created_at": datetime.fromtimestamp(ctime or time.time()),
        })

    return items

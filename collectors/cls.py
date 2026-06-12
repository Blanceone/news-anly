"""财联社 (cls.cn) 实时快讯采集

API 需要签名: SHA1(排序后的参数字符串) 结果再做 MD5
"""
import hashlib
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup


def collect(config: dict) -> list:
    api_url = config["api_url"]
    params = config.get("params", {}).copy()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": config.get("url", ""),
    }
    custom_headers = config.get("headers", {})
    headers.update(custom_headers)

    ts = int(time.time())
    params["last_time"] = str(ts)
    input_str = "&".join(f"{k}={params[k]}" for k in sorted(params))
    sign = hashlib.md5(hashlib.sha1(input_str.encode()).hexdigest().encode()).hexdigest()
    params["sign"] = sign

    resp = requests.get(api_url, params=params, headers=headers, timeout=15)
    resp.encoding = "utf-8"
    data = resp.json()

    items = []
    for item in data.get("data", {}).get("roll_data", []):
        title = item.get("title", "") or BeautifulSoup(item.get("content", ""), "html.parser").get_text()[:80]
        items.append({
            "title": title,
            "content": BeautifulSoup(item.get("content", ""), "html.parser").get_text(),
            "url": f"https://www.cls.cn/detail/{item.get('id')}",
            "source": "cls",
            "source_name": "财联社",
            "created_at": datetime.fromtimestamp(item.get("ctime", time.time())),
        })

    return items

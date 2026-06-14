"""巨潮资讯 (cninfo.com.cn) 上市公司公告采集"""
import time
from datetime import datetime

import requests


def collect(config: dict, since: datetime = None) -> list:
    api_url = config["api_url"]
    base_params = config.get("params", {}).copy()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": config.get("url", ""),
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "http://www.cninfo.com.cn",
    }

    items = []
    page = 1
    max_pages = 5

    while page <= max_pages:
        params = base_params.copy()
        params["pageNum"] = page
        resp = requests.post(api_url, data=params, headers=headers, timeout=15)
        resp.encoding = "utf-8"
        data = resp.json()

        batch = data.get("announcements", [])
        if not batch:
            break

        for ann in batch:
            ann_time = _parse_time(ann.get("announcementTime"))
            if since and ann_time < since:
                return items

            title = ann.get("announcementTitle", "")
            sec_name = ann.get("secName", "")
            sec_code = ann.get("secCode", "")
            adjunct_url = ann.get("adjunctUrl", "")
            items.append({
                "title": f"[{sec_code} {sec_name}] {title}",
                "content": f"{sec_name}({sec_code}) 发布公告: {title}",
                "url": f"http://static.cninfo.com.cn/{adjunct_url}" if adjunct_url else "",
                "source": "cninfo",
                "source_name": "巨潮资讯",
                "created_at": datetime.now(),
                "announcement_date": ann_time,
            })

        total_pages = (data.get("totalAnnouncement", 0) + params["pageSize"] - 1) // params["pageSize"]
        if page >= total_pages:
            break
        page += 1
        time.sleep(0.5)

    return items


def _parse_time(t):
    if isinstance(t, str):
        try:
            return datetime.strptime(t, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    if isinstance(t, (int, float)):
        return datetime.fromtimestamp(t / 1000 if t > 1e10 else t)
    return datetime.now()

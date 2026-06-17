"""信息源监控

PRD 第二章: 信息源分层与监测矩阵
  Tier 1: 政府与监管层 (发改委/工信部/证监会) — 框架预留
  Tier 2: 上市公司官方渠道 (巨潮公告)        — 部分由 cninfo 采集器覆盖
  Tier 3: 海外产业映射                       — 框架预留
  Tier 4: 行业高频数据                       — 框架预留
  Tier 5: 权威财经快讯 (财联社/中证报)       — 由 cls 采集器覆盖
  Tier 6: 市场情绪与草根调研                  — 参考用

当前已实现: Tier 2 (cninfo) + Tier 5 (cls)
其余 Tier 为框架预留，后续按需扩展。
"""
import sqlite3
from datetime import datetime
from config import Config


# 信息源 Tier 定义
TIER_SOURCES = {
    1: {
        "name": "政府与监管层",
        "sources": [
            {"id": "ndrc", "name": "发改委", "url": "https://www.ndrc.gov.cn/", "type": "web"},
            {"id": "miit", "name": "工信部", "url": "https://www.miit.gov.cn/", "type": "web"},
            {"id": "csrc", "name": "证监会", "url": "https://www.csrc.gov.cn/", "type": "web"},
        ],
        "frequency": "每日7:00前",
    },
    2: {
        "name": "上市公司官方",
        "sources": [
            {"id": "cninfo", "name": "巨潮资讯", "url": "http://www.cninfo.com.cn/", "type": "api", "active": True},
        ],
        "frequency": "盘前及盘中",
    },
    3: {
        "name": "海外产业映射",
        "sources": [
            {"id": "nvidia", "name": "英伟达", "url": "https://www.nvidia.com/", "type": "web"},
            {"id": "apple", "name": "苹果", "url": "https://www.apple.com/", "type": "web"},
        ],
        "frequency": "每日盘前",
    },
    4: {
        "name": "行业高频数据",
        "sources": [
            {"id": "cnev", "name": "乘联会", "url": "http://www.cpcaauto.com/", "type": "web"},
            {"id": "semiconductor", "name": "SEMI", "url": "https://www.semi.org/", "type": "web"},
        ],
        "frequency": "每周固定日",
    },
    5: {
        "name": "权威财经快讯",
        "sources": [
            {"id": "cls", "name": "财联社", "url": "https://www.cls.cn/", "type": "api", "active": True},
        ],
        "frequency": "盘中实时",
    },
    6: {
        "name": "市场情绪",
        "sources": [
            {"id": "xueqiu", "name": "雪球", "url": "https://xueqiu.com/", "type": "web"},
        ],
        "frequency": "事件驱动",
    },
}


class SourceMonitor:
    def __init__(self, news_db=None):
        self.news_db = news_db or Config.NEWS_DB

    def get_tier_status(self) -> list:
        """获取各 Tier 信息源的采集状态"""
        statuses = []
        for tier_no, tier_info in TIER_SOURCES.items():
            for src in tier_info["sources"]:
                is_active = src.get("active", False)
                last_fetch = self._get_last_fetch(src["id"]) if is_active else None
                statuses.append({
                    "tier": tier_no,
                    "tier_name": tier_info["name"],
                    "source_id": src["id"],
                    "source_name": src["name"],
                    "url": src["url"],
                    "is_active": is_active,
                    "frequency": tier_info["frequency"],
                    "last_fetch": last_fetch,
                    "status": "active" if is_active else "planned",
                })
        return statuses

    def _get_last_fetch(self, source_id: str) -> str:
        """查询某信息源最近一次采集时间"""
        try:
            with sqlite3.connect(self.news_db) as conn:
                row = conn.execute(
                    "SELECT MAX(created_at) FROM news WHERE source=?",
                    (source_id,)
                ).fetchone()
                return row[0] if row and row[0] else None
        except Exception:
            return None

    def get_news_timeline(self, hours=24, limit=100) -> list:
        """获取信息源采集时间线 (按时间排序)"""
        since = (datetime.now() - __import__('datetime').timedelta(hours=hours)).isoformat()
        try:
            with sqlite3.connect(self.news_db) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT source, source_name, COUNT(*) as cnt,
                           MIN(created_at) as first_at, MAX(created_at) as last_at
                    FROM news
                    WHERE created_at > ?
                    GROUP BY source
                    ORDER BY last_at DESC
                """, (since,)).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def get_source_stats(self) -> dict:
        """获取各信息源的统计信息"""
        stats = {}
        try:
            with sqlite3.connect(self.news_db) as conn:
                rows = conn.execute("""
                    SELECT source, source_name, COUNT(*) as total,
                           SUM(CASE WHEN analyzed=1 THEN 1 ELSE 0 END) as analyzed_count
                    FROM news
                    GROUP BY source
                """).fetchall()
                for r in rows:
                    stats[r[0]] = {
                        "source": r[0],
                        "name": r[1],
                        "total": r[2],
                        "analyzed": r[3],
                    }
        except Exception:
            pass
        return stats

    @staticmethod
    def get_all_tiers() -> dict:
        """返回所有 Tier 定义"""
        return TIER_SOURCES

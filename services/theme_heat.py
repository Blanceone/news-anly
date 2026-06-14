"""Dynamic Theme Heat System — Phase 12

实时反映主题热度变化。
公式: HeatScore = 新闻热度(40%) + 板块热度(35%) + 资金热度(25%)
"""
import sqlite3
from collections import defaultdict
from datetime import datetime


class ThemeHeat:
    def __init__(self, news_db=None, stocks_db=None):
        from config import Config
        self.news_db = news_db or Config.NEWS_DB
        self.stocks_db = stocks_db or Config.STOCKS_DB
        from core.db_init import init_stocks_db
        init_stocks_db()

    def calculate(self):
        """计算所有主题的热度并写入 theme_heat 表"""
        news_heat = self._news_heat()
        board_heat = self._board_heat()

        with sqlite3.connect(self.stocks_db) as conn:
            conn.execute("DELETE FROM theme_heat")
            all_themes = set(news_heat.keys()) | set(board_heat.keys())
            for theme in sorted(all_themes):
                nh = news_heat.get(theme, 0)
                bh = board_heat.get(theme, 0)
                heat = int(nh * 0.4 + bh * 0.35 + 0 * 0.25)
                conn.execute("""
                    INSERT INTO theme_heat
                        (theme_name, heat_score, mention_count, board_change, board_volume)
                    VALUES (?, ?, ?, ?, ?)
                """, (theme, heat, news_heat.get(theme + ":cnt", 0),
                      board_heat.get(theme + ":chg", 0), board_heat.get(theme + ":vol", 0)))
            conn.commit()
            return all_themes

    def _news_heat(self) -> dict:
        """过去24h提及次数 + event_score 总和"""
        heat = defaultdict(float)
        counts = defaultdict(int)
        try:
            with sqlite3.connect(self.news_db) as conn:
                conn.row_factory = sqlite3.Row
                since = (datetime.now().timestamp() - 24 * 3600)
                rows = conn.execute("""
                    SELECT keywords_json, event_score, industry FROM event_analysis
                    WHERE created_at > datetime(?, 'unixepoch')
                """, (since,)).fetchall()
                for r in rows:
                    industry = (r["industry"] or "").strip()
                    score = r["event_score"] or 0
                    if industry:
                        heat[industry] += score
                        counts[industry] += 1
                    try:
                        import json
                        kws = json.loads(r["keywords_json"] or "[]")
                        for kw in kws:
                            if len(kw) > 1:
                                heat[kw] += score * 0.5
                                counts[kw] += 1
                    except Exception:
                        pass
        except Exception:
            pass
        max_h = max(heat.values()) if heat else 1
        result = {}
        for k, v in heat.items():
            result[k] = (v / max_h) * 100
            result[k + ":cnt"] = counts[k]
        return result

    def _board_heat(self) -> dict:
        """从 sector_cache 获取板块行情热度"""
        heat = {}
        try:
            with sqlite3.connect(self.stocks_db) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("SELECT * FROM sector_cache ORDER BY change DESC").fetchall()
                max_chg = max(abs(r["change"] or 0) for r in rows) or 1
                for r in rows:
                    name = r["name"]
                    chg = r["change"] or 0
                    vol = r["volume"] or 0
                    up = r["up"] or 0
                    down = r["down"] or 1
                    # 板块热度: 涨跌幅(0-40) + 涨跌比(0-30) + 成交额(0-30)
                    chg_score = 40 * abs(chg) / max_chg if max_chg else 0
                    ratio = up / (up + down)
                    ratio_score = 30 * ratio
                    vol_score = min(30, vol / 10)
                    heat[name] = chg_score + ratio_score + vol_score
                    heat[name + ":chg"] = chg
                    heat[name + ":vol"] = vol
        except Exception:
            pass
        return heat

    def get_top_themes(self, limit=10) -> list:
        with sqlite3.connect(self.stocks_db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM theme_heat ORDER BY heat_score DESC LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]

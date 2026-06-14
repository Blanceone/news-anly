import sqlite3
from datetime import datetime, timedelta, timezone
from collections import defaultdict

BJT = timezone(timedelta(hours=8))


def to_bjt(ts_str):
    """Format timestamp string to Beijing time (MM-DD HH:MM). DB stores all times in Beijing time (UTC+8)."""
    if not ts_str:
        return ""
    try:
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            # DB 中以北京时间存储，直接格式化
            return dt.strftime("%m-%d %H:%M")
        return dt.astimezone(BJT).strftime("%m-%d %H:%M")
    except Exception:
        # fallback: YYYY-MM-DDTHH:MM:SS → MM-DD HH:MM
        if len(ts_str) >= 16:
            return ts_str[5:10] + " " + ts_str[11:16]
        return ts_str


class TuiDB:
    def __init__(self, news_db=None, stocks_db=None):
        from config import Config
        self.db_path = news_db or Config.NEWS_DB
        self.stocks_db = stocks_db or Config.STOCKS_DB
        from core.db_init import init_news_db, init_stocks_db
        init_news_db()
        init_stocks_db()

    def _conn(self):
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    def _sconn(self):
        c = sqlite3.connect(self.stocks_db)
        c.row_factory = sqlite3.Row
        return c

    def recent_news(self, hours=72, limit=50):
        since = (datetime.now() - timedelta(hours=hours)).isoformat()
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT id, title, source_name, category, sentiment, created_at
                FROM news WHERE created_at > ? ORDER BY created_at DESC LIMIT ?
            """, (since, limit)).fetchall()
            return [dict(r) for r in rows]

    def top_stocks(self, limit=20):
        with self._sconn() as conn:
            rows = conn.execute("""
                SELECT stock_code, stock_name, total_score, event_score,
                       benefit_score, market_score, event_count, top_events
                FROM stock_score WHERE score_date = date('now')
                GROUP BY stock_code
                ORDER BY total_score DESC LIMIT ?
            """, (limit,)).fetchall()

            if not rows:
                rows = conn.execute("""
                    SELECT stock_code, stock_name, total_score, event_score,
                           benefit_score, market_score, event_count, top_events
                    FROM stock_score
                    GROUP BY stock_code
                    ORDER BY MAX(id) DESC, total_score DESC LIMIT ?
                """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    def _tushare_pro(self):
        import tushare as ts, config
        return ts.pro_api(config.Config().TUSHARE_TOKEN)

    def all_sectors(self):
        """行业板块数据 — Tushare主力 + KG主题 + AKShare补充 + DB缓存"""
        import time as _time
        cache = getattr(self, "_sector_cache", None)
        cache_time = getattr(self, "_sector_cache_time", 0)
        if cache and (_time.time() - cache_time) < 60:
            return cache
        sectors = self._ts_sectors()
        seen = {s["name"] for s in sectors}
        # 合并KG主题
        for t in self._kg_themes():
            if t["name"] not in seen:
                sectors.append(t)
                seen.add(t["name"])
        # 合并AKShare概念板块
        for c in self._ak_concept_sectors():
            if c["name"] not in seen:
                sectors.append(c)
                seen.add(c["name"])
        if not sectors:
            sectors = self._load_sector_cache()
        sectors.sort(key=lambda s: -s.get("change", 0))
        self._sector_cache = sectors
        self._sector_cache_time = _time.time()
        return sectors

    def _kg_themes(self):
        """从theme_stock_mapping + event_analysis + KG实体 + 静态兜底 获取主题"""
        themes = set()
        try:
            with self._sconn() as conn:
                rows = conn.execute("SELECT DISTINCT theme_name FROM theme_stock_mapping").fetchall()
                for r in rows:
                    themes.add(r[0])
                rows = conn.execute("""
                    SELECT DISTINCT name FROM kg_entity WHERE entity_type='theme'
                """).fetchall()
                for r in rows:
                    themes.add(r[0])
            with self._conn() as conn:
                rows = conn.execute("""
                    SELECT DISTINCT industry FROM event_analysis
                    WHERE industry IS NOT NULL AND industry != ''
                    AND created_at > datetime('now', '-72 hours')
                """).fetchall()
                for r in rows:
                    themes.add(r[0])
        except Exception:
            pass
        # Static fallback: ensure these are always visible
        for name in ["人工智能", "算力基础设施", "半导体", "机器人", "创新药",
                      "先进封装", "具身智能", "低空经济", "新能源", "CPO/光通信",
                      "AI芯片", "光模块", "封测", "减速器", "CXO",
                      "光伏", "锂电池", "储能", "人形机器人", "智能驾驶"]:
            themes.add(name)
        return [{"name": t, "change": 0, "up": 0, "down": 0, "volume": 0} for t in sorted(themes)]

    def _ak_concept_sectors(self):
        """AKShare概念板块"""
        try:
            import akshare as ak
            df = ak.stock_board_concept_spot_em()
            sectors = []
            for _, row in df.iterrows():
                d = {}
                for k, v in row.items():
                    k = k.strip()
                    if "板块名称" in k or "名称" in k:
                        d["name"] = str(v)
                    elif "涨跌幅" in k:
                        d["change"] = round(float(v), 2) if v else 0.0
                    elif "上涨" in k:
                        d["up"] = int(v) if v else 0
                    elif "下跌" in k:
                        d["down"] = int(v) if v else 0
                    elif "成交额" in k:
                        d["volume"] = round(float(v) / 1e8, 1) if v else 0.0
                if d.get("name"):
                    d["_source"] = "concept"
                    sectors.append(d)
            return sectors
        except Exception:
            return []

    def _last_trade_date(self):
        """获取最近一个交易日"""
        import datetime
        d = datetime.date.today()
        while True:
            if d.weekday() < 5:
                return d.strftime("%Y%m%d")
            d -= datetime.timedelta(days=1)

    def _ts_sectors(self):
        """Tushare主力：stock_basic(industry) + daily(pct_chg) → 行业聚合"""
        try:
            pro = self._tushare_pro()
            tdate = self._last_trade_date()
            # 获取全部股票行业分类
            sb = pro.stock_basic(fields='ts_code,industry')
            industry_map = {}
            for _, row in sb.iterrows():
                ind = str(row.get("industry", "") or "").strip()
                code = str(row.get("ts_code", ""))
                if ind and code:
                    industry_map.setdefault(ind, []).append(code)
            if not industry_map:
                return []
            # 获取最近交易日全部股票行情
            daily = pro.daily(trade_date=tdate)
            chg_map = {}
            for _, row in daily.iterrows():
                chg_map[str(row["ts_code"])] = {
                    "pct_chg": float(row.get("pct_chg", 0)),
                    "amount": float(row.get("amount", 0)) if row.get("amount") else 0,
                }
            # 按行业聚合
            sectors = []
            for ind, codes in industry_map.items():
                changes = []
                up = down = 0
                total_vol = 0.0
                for c in codes:
                    d = chg_map.get(c)
                    if d:
                        chg = d["pct_chg"]
                        changes.append(chg)
                        total_vol += d["amount"]
                        if chg > 0:
                            up += 1
                        elif chg < 0:
                            down += 1
                avg = round(sum(changes) / len(changes), 2) if changes else 0
                sectors.append({
                    "name": ind,
                    "change": avg,
                    "up": up,
                    "down": down,
                    "volume": round(total_vol / 1e8, 1),
                })
            sectors.sort(key=lambda s: -s["change"])
            if sectors:
                self._save_sector_cache(sectors)
            return sectors
        except Exception as e:
            print(f"  [Tushare] 行业聚合失败: {e}")
            return []

    def _ak_sectors(self):
        """AKShare补充：stock_board_industry_spot_em"""
        try:
            import akshare as ak
            df = ak.stock_board_industry_spot_em()
            sectors = []
            for _, row in df.iterrows():
                d = {}
                for k, v in row.items():
                    k = k.strip()
                    if "板块名称" in k or "名称" in k:
                        d["name"] = str(v)
                    elif "涨跌幅" in k:
                        d["change"] = round(float(v), 2) if v else 0.0
                    elif "上涨" in k:
                        d["up"] = int(v) if v else 0
                    elif "下跌" in k:
                        d["down"] = int(v) if v else 0
                    elif "成交额" in k:
                        d["volume"] = round(float(v) / 1e8, 1) if v else 0.0
                if d.get("name"):
                    sectors.append(d)
            if sectors:
                self._save_sector_cache(sectors)
            return sectors
        except Exception:
            return []

    def _save_sector_cache(self, sectors):
        try:
            with self._sconn() as conn:
                conn.execute("DELETE FROM sector_cache")
                for s in sectors:
                    conn.execute(
                        "INSERT OR REPLACE INTO sector_cache (name, change, up, down, volume) VALUES (?,?,?,?,?)",
                        (s["name"], s.get("change", 0), s.get("up", 0), s.get("down", 0), s.get("volume", 0)))
                conn.commit()
        except Exception:
            pass

    def _load_sector_cache(self):
        try:
            with self._sconn() as conn:
                rows = conn.execute("SELECT * FROM sector_cache ORDER BY change DESC").fetchall()
                if rows:
                    return [dict(r) for r in rows]
        except Exception:
            pass
        return [{"name": n, "change": 0, "up": 0, "down": 0, "volume": 0}
                for n in self._STATIC_SECTORS]

    _STATIC_SECTORS = [
        "银行", "证券", "保险", "房地产开发", "汽车整车", "半导体及元件", "电力",
        "计算机应用", "化学制药", "国防军工", "消费电子", "有色金属", "医疗器械",
        "电力设备", "煤炭开采加工", "建筑装饰", "饮料制造", "汽车零部件", "钢铁",
        "传媒", "通信设备", "食品加工制造", "环保", "电子化学品", "机场航运",
        "物流", "种植业与林业", "养殖业", "纺织服装", "包装印刷", "专用设备",
        "通用设备", "自动化设备", "仪器仪表", "化学制品", "新材料", "化工合成材料",
        "化工新材料", "石油加工贸易", "医药商业", "中药", "生物制品", "医疗服务",
        "零售", "贸易", "景点及旅游", "酒店及餐饮", "教育", "公路铁路运输",
        "港口航运", "非汽车交运", "汽车服务", "石油矿业开采", "燃气",
        "半导体", "白酒概念", "人工智能", "机器人", "低空经济", "创新药",
        "智能驾驶", "固态电池", "锂电池", "钠离子电池", "光伏", "风电",
        "储能", "氢能源", "核电", "数字经济", "东数西算", "信创", "算力",
        "数据要素", "数据安全", "CPO", "光通信",
    ]

    def sector_stocks(self, sector_name):
        """行业成分股 — Tushare主力 + KG映射 + AKShare补充"""
        stocks = self._ts_sector_stocks(sector_name)
        if not stocks:
            stocks = self._kg_sector_stocks(sector_name)
        if not stocks:
            stocks = self._ak_sector_stocks(sector_name)
        if not stocks:
            stocks = self._ak_concept_stocks(sector_name)
        return stocks

    def _kg_sector_stocks(self, sector_name):
        """从theme_stock_mapping获取主题对应股票"""
        try:
            with self._sconn() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT stock_code, stock_name, benefit_level, benefit_reason
                    FROM theme_stock_mapping
                    WHERE theme_name = ?
                    ORDER BY benefit_level ASC
                """, (sector_name,)).fetchall()
                if not rows:
                    return []
                stocks = []
                for r in rows:
                    d = dict(r)
                    d["change"] = 0
                    stocks.append(d)
                return stocks
        except Exception:
            return []

    def _ak_concept_stocks(self, sector_name):
        """AKShare概念成分股"""
        try:
            import akshare as ak
            df = ak.stock_board_concept_cons_em(symbol=sector_name)
            stocks = []
            for _, row in df.iterrows():
                d = {}
                for k, v in row.items():
                    k = k.strip()
                    if "代码" in k:
                        d["stock_code"] = str(v)
                    elif "名称" in k:
                        d["stock_name"] = str(v)
                    elif "涨跌幅" in k:
                        d["change"] = round(float(v), 2) if v else 0.0
                if d.get("stock_code") and d.get("stock_name"):
                    stocks.append(d)
            stocks.sort(key=lambda s: -s.get("change", 0))
            return stocks
        except Exception:
            return []

    def _ts_sector_stocks(self, sector_name):
        """Tushare：stock_basic(industry过滤) + daily_basic(行情)"""
        try:
            pro = self._tushare_pro()
            sb = pro.stock_basic(fields='ts_code,name,industry')
            codes_in = sb[sb['industry'] == sector_name]
            if codes_in.empty:
                return []
            tdate = self._last_trade_date()
            daily = pro.daily(trade_date=tdate)
            chg_map = {}
            for _, row in daily.iterrows():
                chg_map[str(row["ts_code"])] = float(row.get("pct_chg", 0))
            stocks = []
            for _, row in codes_in.iterrows():
                code = str(row["ts_code"])
                stocks.append({
                    "stock_code": code,
                    "stock_name": str(row.get("name", "")),
                    "change": chg_map.get(code, 0),
                })
            stocks.sort(key=lambda s: -s["change"])
            return stocks
        except Exception as e:
            print(f"  [Tushare] 成分股获取失败: {e}")
            return []

    def _ak_sector_stocks(self, sector_name):
        """AKShare补充：stock_board_industry_cons_em"""
        try:
            import akshare as ak
            df = ak.stock_board_industry_cons_em(symbol=sector_name)
            stocks = []
            for _, row in df.iterrows():
                d = {}
                for k, v in row.items():
                    k = k.strip()
                    if "代码" in k:
                        d["stock_code"] = str(v)
                    elif "名称" in k:
                        d["stock_name"] = str(v)
                    elif "涨跌幅" in k:
                        d["change"] = round(float(v), 2) if v else 0.0
                if d.get("stock_code") and d.get("stock_name"):
                    stocks.append(d)
            stocks.sort(key=lambda s: -s.get("change", 0))
            return stocks
        except Exception:
            return []

    def industry_sectors(self):
        """仅Tushare行业板块（有实时行情）"""
        sectors = self._ts_sectors()
        if not sectors:
            sectors = self._ak_sectors()
        if not sectors:
            sectors = self._load_sector_cache()
        return sectors

    def concept_themes(self):
        """概念主题（KG主题 + AKShare概念板块），含热度/股票数"""
        themes = []
        seen = set()
        # KG 主题 → theme_stock_mapping
        try:
            with self._sconn() as conn:
                rows = conn.execute("""
                    SELECT t.theme_name, t.theme_key, COUNT(DISTINCT t.stock_code) as stock_count
                    FROM theme_stock_mapping t GROUP BY t.theme_key
                """).fetchall()
                for r in rows:
                    themes.append({
                        "name": r["theme_name"],
                        "key": r["theme_key"],
                        "stock_count": r["stock_count"],
                        "change": 0, "up": 0, "down": 0, "volume": 0,
                        "source": "kg",
                    })
                    seen.add(r["theme_name"])
        except Exception:
            pass
        # AKShare 概念板块（有实时行情）
        try:
            import akshare as ak
            df = ak.stock_board_concept_spot_em()
            for _, row in df.iterrows():
                d = {}
                for k, v in row.items():
                    k = k.strip()
                    if "板块名称" in k or "名称" in k:
                        d["name"] = str(v)
                    elif "涨跌幅" in k:
                        d["change"] = round(float(v), 2) if v else 0.0
                    elif "上涨" in k:
                        d["up"] = int(v) if v else 0
                    elif "下跌" in k:
                        d["down"] = int(v) if v else 0
                    elif "成交额" in k:
                        d["volume"] = round(float(v) / 1e8, 1) if v else 0.0
                if d.get("name") and d["name"] not in seen:
                    d["source"] = "concept"
                    d["stock_count"] = 0
                    themes.append(d)
                    seen.add(d["name"])
        except Exception:
            pass
        # 静态兜底：确保未在theme_stock_mapping中的主题仍然可见
        static_names = [
            "人工智能", "算力基础设施", "半导体", "机器人", "创新药",
            "先进封装", "具身智能", "低空经济", "新能源", "CPO/光通信",
            "AI芯片", "光模块", "封测", "减速器", "CXO",
            "光伏", "锂电池", "储能", "人形机器人", "智能驾驶",
            "玻璃基板",
        ]
        for name in static_names:
            if name not in seen:
                themes.append({
                    "name": name, "key": name, "stock_count": 0,
                    "change": 0, "up": 0, "down": 0, "volume": 0,
                    "source": "static",
                })
                seen.add(name)
        themes.sort(key=lambda t: -t.get("change", 0))
        return themes

    def hot_themes(self):
        with self._sconn() as conn:
            rows = conn.execute("""
                SELECT theme_key, theme_name, COUNT(DISTINCT stock_code) as stock_count
                FROM theme_stock_mapping GROUP BY theme_key ORDER BY stock_count DESC
            """).fetchall()
            themes = [dict(r) for r in rows]

        with self._conn() as conn:
            event_rows = conn.execute("""
                SELECT e.industry, COUNT(*) as cnt
                FROM event_analysis e
                WHERE e.created_at > datetime('now', '-24 hours')
                GROUP BY e.industry ORDER BY cnt DESC
            """).fetchall()
            for r in event_rows:
                d = dict(r)
                name = d["industry"] or "其他"
                if not any(t["theme_name"] == name for t in themes):
                    themes.append({"theme_key": name, "theme_name": name,
                                   "stock_count": d["cnt"]})
            return themes

    def stock_detail(self, stock_code):
        with self._sconn() as sconn:
            score = sconn.execute("""
                SELECT * FROM stock_score WHERE stock_code = ?
                ORDER BY id DESC LIMIT 1
            """, (stock_code,)).fetchone()
            mapping_rows = sconn.execute("""
                SELECT event_id, benefit_level, benefit_score, match_reason
                FROM event_stock_mapping WHERE stock_code = ?
                ORDER BY id DESC LIMIT 20
            """, (stock_code,)).fetchall()
            themes = sconn.execute("""
                SELECT theme_name, benefit_level, benefit_reason
                FROM theme_stock_mapping WHERE stock_code = ?
            """, (stock_code,)).fetchall()
        # Cross-DB merge: get event details from news.db
        event_ids = tuple(r["event_id"] for r in mapping_rows) if mapping_rows else (-1,)
        events = []
        if mapping_rows:
            emap = {r["event_id"]: r for r in mapping_rows}
            try:
                placeholders = ",".join("?" for _ in event_ids)
                with self._conn() as nconn:
                    nrows = nconn.execute(f"""
                        SELECT event_id, event_type, industry, importance,
                               sentiment, event_score, ai_summary, created_at
                        FROM event_analysis WHERE event_id IN ({placeholders})
                    """, tuple(event_ids)).fetchall()
                    for r in nrows:
                        d = dict(r)
                        m = emap[d["event_id"]]
                        d["benefit_level"] = m["benefit_level"]
                        d["benefit_score"] = m["benefit_score"]
                        d["match_reason"] = m["match_reason"]
                        events.append(d)
                events.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            except Exception:
                pass
        # Market confirmation from stocks.db
        market = []
        if event_ids and event_ids != (-1,):
            with self._sconn() as sconn2:
                mrows = sconn2.execute(f"""
                    SELECT event_id, board_name, sector_change, confirmation_score
                    FROM market_confirmation
                    WHERE event_id IN ({placeholders})
                    ORDER BY calculated_at DESC
                """, tuple(event_ids)).fetchall()
                market = [dict(r) for r in mrows]
        return {
            "score": dict(score) if score else None,
            "events": events,
            "themes": [dict(r) for r in themes],
            "market_confirmations": market,
        }

    def all_stocks_summary(self):
        with self._sconn() as conn:
            rows = conn.execute("""
                SELECT s.stock_code, s.stock_name, MAX(s.total_score) as total_score,
                       MAX(s.event_count) as event_count,
                       COALESCE(t.theme_count, 0) as theme_count
                FROM stock_score s
                LEFT JOIN (
                    SELECT stock_code, COUNT(*) as theme_count
                    FROM theme_stock_mapping GROUP BY stock_code
                ) t ON s.stock_code = t.stock_code
                WHERE s.score_date = date('now')
                GROUP BY s.stock_code
                ORDER BY total_score DESC
            """).fetchall()
            if not rows:
                rows = conn.execute("""
                    SELECT s.stock_code, s.stock_name, MAX(s.total_score) as total_score,
                           MAX(s.event_count) as event_count,
                           COALESCE(t.theme_count, 0) as theme_count
                    FROM stock_score s
                    LEFT JOIN (
                        SELECT stock_code, COUNT(*) as theme_count
                        FROM theme_stock_mapping GROUP BY stock_code
                    ) t ON s.stock_code = t.stock_code
                    GROUP BY s.stock_code
                    ORDER BY total_score DESC LIMIT 50
                """).fetchall()
            return [dict(r) for r in rows]

    def event_list(self, hours=72, limit=50):
        try:
            since = (datetime.now() - timedelta(hours=hours)).isoformat()
            with self._conn() as conn:
                rows = conn.execute("""
                    SELECT e.*, n.title as news_title, n.source_name as news_source, n.url as news_url
                    FROM event_analysis e
                    LEFT JOIN news n ON e.source_id = n.id
                    WHERE e.created_at > ? ORDER BY e.created_at DESC LIMIT ?
                """, (since, limit)).fetchall()
                events = [dict(r) for r in rows]
            # Merge market confirmation from stocks.db
            event_ids = tuple(e["event_id"] for e in events) if events else (-1,)
            if event_ids != (-1,):
                placeholders = ",".join("?" for _ in event_ids)
                with self._sconn() as sconn:
                    mrows = sconn.execute(f"""
                        SELECT event_id, confirmation_score
                        FROM market_confirmation
                        WHERE event_id IN ({placeholders})
                    """, tuple(event_ids)).fetchall()
                    mcmap = {r["event_id"]: r["confirmation_score"] for r in mrows}
                    for e in events:
                        e["market_score"] = mcmap.get(e["event_id"], 0)
            else:
                for e in events:
                    e["market_score"] = 0
            return events
        except Exception:
            return []

    def event_stocks(self, event_id):
        with self._sconn() as conn:
            rows = conn.execute("""
                SELECT es.* FROM event_stock_mapping es
                WHERE es.event_id = ?
            """, (event_id,)).fetchall()
            return [dict(r) for r in rows]

    def theme_stocks(self, theme_key):
        with self._sconn() as conn:
            rows = conn.execute("""
                SELECT * FROM theme_stock_mapping WHERE theme_key = ?
            """, (theme_key,)).fetchall()
            return [dict(r) for r in rows]

    def stats(self):
        try:
            with self._conn() as conn:
                news_count = conn.execute("SELECT COUNT(*) FROM news").fetchone()[0]
                event_count = conn.execute("SELECT COUNT(*) FROM event_analysis").fetchone()[0]
            with self._sconn() as conn:
                stock_count = conn.execute("SELECT COUNT(DISTINCT stock_code) FROM stock_score").fetchone()[0]
            return {"news": news_count, "events": event_count, "stocks": stock_count}
        except Exception:
            return {"news": 0, "events": 0, "stocks": 0}

    def theme_candidates(self, limit=50):
        try:
            with self._sconn() as conn:
                rows = conn.execute("""
                    SELECT * FROM theme_candidate
                    ORDER BY mention_count DESC, last_seen DESC LIMIT ?
                """, (limit,)).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def event_clusters(self, limit=30):
        try:
            with self._sconn() as conn:
                rows = conn.execute("""
                    SELECT * FROM event_cluster
                    ORDER BY event_count DESC, last_seen DESC LIMIT ?
                """, (limit,)).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def cluster_events(self, cluster_id):
        try:
            with self._sconn() as sconn:
                event_ids = sconn.execute("""
                    SELECT event_id FROM event_cluster_map WHERE cluster_id=?
                """, (cluster_id,)).fetchall()
                eids = tuple(r[0] for r in event_ids)
                if not eids:
                    return []
            with self._conn() as nconn:
                placeholders = ",".join("?" for _ in eids)
                rows = nconn.execute(f"""
                    SELECT e.*, n.title, n.source_name
                    FROM event_analysis e
                    JOIN news n ON e.source_id = n.id
                    WHERE e.event_id IN ({placeholders})
                    ORDER BY e.event_score DESC
                """, eids).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    # ---- V3 TUI pages ----

    def theme_heat_list(self, limit=30):
        try:
            with self._sconn() as conn:
                rows = conn.execute("""
                    SELECT theme_name, raw_heat, decay_heat, board_change,
                           board_volume, up_stock_count, down_stock_count,
                           limitup_count, heat, last_active_time
                    FROM theme_heat
                    ORDER BY decay_heat DESC LIMIT ?
                """, (limit,)).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def lifecycle_stats(self):
        try:
            with self._sconn() as conn:
                rows = conn.execute("""
                    SELECT status, COUNT(*) as cnt,
                           ROUND(AVG(event_count), 1) as avg_events
                    FROM event_cluster
                    WHERE status IS NOT NULL
                    GROUP BY status ORDER BY status
                """).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def lifecycle_clusters(self, status=None, limit=20):
        try:
            with self._sconn() as conn:
                if status:
                    rows = conn.execute("""
                        SELECT * FROM event_cluster
                        WHERE status=? ORDER BY event_count DESC LIMIT ?
                    """, (status, limit)).fetchall()
                else:
                    rows = conn.execute("""
                        SELECT * FROM event_cluster
                        ORDER BY event_count DESC LIMIT ?
                    """, (limit,)).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def stock_profile_list(self, limit=30):
        try:
            with self._sconn() as conn:
                rows = conn.execute("""
                    SELECT * FROM stock_profile
                    ORDER BY leader_score DESC LIMIT ?
                """, (limit,)).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def backtest_results(self, limit=20):
        try:
            with self._sconn() as conn:
                rows = conn.execute("""
                    SELECT * FROM backtest_result
                    ORDER BY created_at DESC LIMIT ?
                """, (limit,)).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def backtest_trades_by_id(self, bt_id, limit=50):
        try:
            with self._sconn() as conn:
                rows = conn.execute("""
                    SELECT * FROM backtest_trades
                    WHERE backtest_id=?
                    ORDER BY return_rate DESC LIMIT ?
                """, (bt_id, limit)).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

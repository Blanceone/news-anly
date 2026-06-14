"""评分系统 — Phase 13

V2 公式：
  TotalScore = EventScore×20% + BenefitScore×25% + MarketScore×20%
             + ThemeHeat×20% + ClusterHeat×15%
"""
import sqlite3
from collections import defaultdict
from datetime import datetime


class ScoringEngine:
    def __init__(self, db_path=None):
        from config import Config
        self.db_path = db_path or Config.STOCKS_DB
        self._init_table()

    def _init_table(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS stock_score (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_code TEXT NOT NULL,
                    stock_name TEXT NOT NULL,
                    score_date TEXT NOT NULL,
                    event_score REAL DEFAULT 0,
                    benefit_score REAL DEFAULT 0,
                    market_score REAL DEFAULT 0,
                    financial_score REAL DEFAULT 0,
                    technical_score REAL DEFAULT 0,
                    capital_score REAL DEFAULT 0,
                    total_score REAL DEFAULT 0,
                    event_count INTEGER DEFAULT 0,
                    top_events TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS recommendation_result (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_code TEXT NOT NULL,
                    stock_name TEXT NOT NULL,
                    strategy_type TEXT NOT NULL,
                    rank_no INTEGER,
                    score REAL,
                    recommendation_reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def calculate(self, hours=24) -> list:
        today = datetime.now().strftime("%Y-%m-%d")
        since = (datetime.now().timestamp() - hours * 3600)

        event_stocks = self._load_event_stocks(since)
        stock_data = self._aggregate(event_stocks)
        results = self._rank(stock_data)

        self._save(today, results)
        return results

    def _load_event_stocks(self, since_ts) -> list:
        from config import Config
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT
                    es.stock_code, es.stock_name,
                    es.benefit_score, es.benefit_level,
                    es.event_id,
                    COALESCE(mc.confirmation_score, 0) as market_score
                FROM event_stock_mapping es
                LEFT JOIN market_confirmation mc ON es.event_id = mc.event_id
            """).fetchall()
        event_ids = [r["event_id"] for r in rows]
        event_map = {}
        if event_ids:
            placeholders = ",".join("?" for _ in event_ids)
            with sqlite3.connect(Config.NEWS_DB) as econn:
                econn.row_factory = sqlite3.Row
                erows = econn.execute(f"""
                    SELECT event_id, event_score, event_type, importance,
                           sentiment, ai_summary, created_at
                    FROM event_analysis
                    WHERE event_id IN ({placeholders})
                      AND created_at > datetime(?, 'unixepoch')
                """, (*event_ids, since_ts)).fetchall()
                event_map = {r["event_id"]: dict(r) for r in erows}
        result = []
        for r in rows:
            e = event_map.get(r["event_id"])
            if e is None:
                continue
            result.append({
                "stock_code": r["stock_code"],
                "stock_name": r["stock_name"],
                "benefit_score": r["benefit_score"],
                "benefit_level": r["benefit_level"],
                "event_score": e["event_score"],
                "event_type": e["event_type"],
                "importance": e["importance"],
                "sentiment": e["sentiment"],
                "ai_summary": e["ai_summary"],
                "event_id": r["event_id"],
                "market_score": r["market_score"],
            })
        return result

    def _aggregate(self, rows: list) -> dict:
        stocks = defaultdict(lambda: {
            "stock_name": "",
            "event_scores": [],
            "benefit_scores": [],
            "market_scores": [],
            "events": [],
            "event_count": 0,
        })
        for r in rows:
            code = r["stock_code"]
            s = stocks[code]
            s["stock_name"] = r["stock_name"]
            s["event_scores"].append(r["event_score"] or 0)
            s["benefit_scores"].append(r["benefit_score"] or 0)
            s["market_scores"].append(r["market_score"] or 0)
            s["events"].append({
                "event_id": r["event_id"],
                "type": r["event_type"],
                "importance": r["importance"],
                "sentiment": r["sentiment"],
                "summary": (r["ai_summary"] or "")[:80],
            })
            s["event_count"] += 1
        return dict(stocks)

    def _load_theme_heat(self) -> dict:
        """加载主题热度 {theme_name: heat_score}"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute("SELECT theme_name, heat_score FROM theme_heat").fetchall()
                return {r[0]: (r[1] or 0) for r in rows}
        except Exception:
            return {}

    def _load_cluster_scores(self, event_ids: list) -> dict:
        """加载事件簇热度 {event_id: cluster_heat_score}"""
        if not event_ids:
            return {}
        try:
            with sqlite3.connect(self.db_path) as conn:
                placeholders = ",".join("?" for _ in event_ids)
                rows = conn.execute(f"""
                    SELECT m.event_id, c.heat_score as cluster_heat,
                           c.event_count as cluster_count
                    FROM event_cluster_map m
                    JOIN event_cluster c ON m.cluster_id = c.cluster_id
                    WHERE m.event_id IN ({placeholders})
                """, event_ids).fetchall()
                # cluster_heat = min(100, cluster_count * 10 + heat_score)
                return {r[0]: min(100, (r[1] or 0) + (r[2] or 1) * 10) for r in rows}
        except Exception:
            return {}

    def _resolve_stock_themes(self, stock_code: str) -> list:
        """查找股票所属的主题（从 theme_stock_mapping）"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    "SELECT theme_name FROM theme_stock_mapping WHERE stock_code=?",
                    (stock_code,)
                ).fetchall()
                return [r[0] for r in rows]
        except Exception:
            return []

    def _rank(self, stock_data: dict) -> list:
        theme_heat = self._load_theme_heat()
        all_event_ids = list({e["event_id"]
                              for d in stock_data.values()
                              for e in d["events"]})
        cluster_scores = self._load_cluster_scores(all_event_ids)

        results = []
        for code, data in stock_data.items():
            event_score = max(data["event_scores"]) if data["event_scores"] else 0
            benefit_score = max(data["benefit_scores"]) if data["benefit_scores"] else 0
            market_score = max(data["market_scores"]) if data["market_scores"] else 0

            # 主题热度: 取股票所属主题的最大热度
            themes = self._resolve_stock_themes(code)
            theme_heat_val = max((theme_heat.get(t, 0) for t in themes), default=0)

            # 簇热度: 事件所在簇的最高评分（去重）
            cluster_max = max(
                (cluster_scores.get(e["event_id"], 0) for e in data["events"]),
                default=0
            )

            total = (event_score * 0.2 + benefit_score * 0.25
                     + market_score * 0.2 + theme_heat_val * 0.2
                     + cluster_max * 0.15)
            top_events = sorted(data["events"], key=lambda x: -x.get("event_id", 0))[:3]
            results.append({
                "stock_code": code,
                "stock_name": data["stock_name"],
                "event_score": event_score,
                "benefit_score": benefit_score,
                "market_score": market_score,
                "theme_heat": round(theme_heat_val),
                "cluster_heat": round(cluster_max),
                "financial_score": 0,
                "technical_score": 0,
                "capital_score": 0,
                "total_score": round(total),
                "event_count": data["event_count"],
                "top_events": top_events,
            })
        results.sort(key=lambda x: -x["total_score"])
        for i, r in enumerate(results, 1):
            r["rank"] = i
        return results

    def _save(self, score_date: str, results: list):
        with sqlite3.connect(self.db_path) as conn:
            for r in results:
                conn.execute("""
                    INSERT INTO stock_score
                        (stock_code, stock_name, score_date,
                         event_score, benefit_score, market_score,
                         financial_score, technical_score, capital_score,
                         total_score, event_count, top_events)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    r["stock_code"], r["stock_name"], score_date,
                    r["event_score"], r["benefit_score"],
                    r["market_score"], r["financial_score"],
                    r["technical_score"], r["capital_score"],
                    r["total_score"], r["event_count"],
                    str(r["top_events"]),
                ))
                conn.execute("""
                    INSERT INTO recommendation_result
                        (stock_code, stock_name, strategy_type, rank_no, score, recommendation_reason)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    r["stock_code"], r["stock_name"], "SHORT",
                    r["rank"], r["total_score"],
                    f"事件{r['event_score']}*20% + 受益{r['benefit_score']}*25% + "
                    f"市场{r['market_score']}*20% + 热度{r.get('theme_heat',0)}*20%"
                ))
            conn.commit()
        print(f"  [评分] 已计算 {len(results)} 只股票的综合评分(V2)")

    def get_top_stocks(self, limit=20, strategy="SHORT") -> list:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT r.*, s.stock_name, s.industry
                FROM recommendation_result r
                LEFT JOIN stock_basic s ON r.stock_code = s.stock_code
                WHERE r.strategy_type=?
                ORDER BY r.created_at DESC, r.score DESC
                LIMIT ?
            """, (strategy, limit)).fetchall()
            return [dict(r) for r in rows]

"""评分系统 — Phase 6 (V3)

V3 公式：
  TotalScore = EventScore×15% + BenefitScore(分层)×20% + MarketScore×15%
             + ThemeHeat(衰减)×15% + ClusterHeat(生命周期)×10%
             + LeaderScore×15% + LifecycleScore×10%
"""
import sqlite3
from collections import defaultdict
from datetime import datetime


_LIFECYCLE_WEIGHTS = {
    "BIRTH": 0.8,
    "GROWING": 1.0,
    "PEAK": 0.7,
    "DECLINING": 0.3,
    "DEAD": 0.0,
}


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
                    COALESCE(es.benefit_type, 'DIRECT') as benefit_type,
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
        _BENEFIT_WEIGHTS = {"DIRECT": 1.0, "INDIRECT": 0.8, "SENTIMENT": 0.5}
        result = []
        for r in rows:
            e = event_map.get(r["event_id"])
            if e is None:
                continue
            btype = r["benefit_type"] or "DIRECT"
            raw_score = r["benefit_score"] or 0
            weighted = int(raw_score * _BENEFIT_WEIGHTS.get(btype, 0.5))
            result.append({
                "stock_code": r["stock_code"],
                "stock_name": r["stock_name"],
                "benefit_score": weighted,
                "benefit_raw": raw_score,
                "benefit_level": r["benefit_level"],
                "benefit_type": btype,
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
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    "SELECT theme_name, COALESCE(CAST(decay_heat AS REAL), heat_score, 0) FROM theme_heat"
                ).fetchall()
                return {r[0]: float(r[1] or 0) for r in rows}
        except Exception:
            return {}

    def _load_cluster_scores(self, event_ids: list) -> dict:
        if not event_ids:
            return {}
        try:
            with sqlite3.connect(self.db_path) as conn:
                placeholders = ",".join("?" for _ in event_ids)
                rows = conn.execute(f"""
                    SELECT m.event_id,
                           COALESCE(CAST(c.heat_score AS REAL), 0) as cluster_heat,
                           COALESCE(c.event_count, 1) as cluster_count,
                           COALESCE(c.status, 'BIRTH') as lifecycle_status
                    FROM event_cluster_map m
                    JOIN event_cluster c ON m.cluster_id = c.cluster_id
                    WHERE m.event_id IN ({placeholders})
                """, event_ids).fetchall()
                result = {}
                for r in rows:
                    lw = _LIFECYCLE_WEIGHTS.get(r["lifecycle_status"], 0.5)
                    base = min(100, float(r["cluster_heat"] or 0) + (int(r["cluster_count"] or 1) * 10))
                    result[r[0]] = {
                        "heat": base,
                        "lifecycle_weight": lw,
                        "lifecycle_score": base * lw,
                    }
                return result
        except Exception:
            return {}

    def _resolve_stock_themes(self, stock_code: str) -> list:
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    "SELECT theme_name FROM theme_stock_mapping WHERE stock_code=?",
                    (stock_code,)
                ).fetchall()
                return [r[0] for r in rows]
        except Exception:
            return []

    def _load_leader_score(self, stock_code: str) -> float:
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    "SELECT leader_score FROM stock_profile WHERE stock_code=?",
                    (stock_code,)
                ).fetchone()
                return float(row[0]) if row and row[0] is not None else 0
        except Exception:
            return 0

    def _rank(self, stock_data: dict) -> list:
        theme_heat = self._load_theme_heat()
        all_event_ids = list({e["event_id"]
                              for d in stock_data.values()
                              for e in d["events"]})
        cluster_data = self._load_cluster_scores(all_event_ids)

        results = []
        for code, data in stock_data.items():
            event_score = max(data["event_scores"]) if data["event_scores"] else 0
            benefit_score = max(data["benefit_scores"]) if data["benefit_scores"] else 0
            market_score = max(data["market_scores"]) if data["market_scores"] else 0

            # 主题热度(衰减后)
            themes = self._resolve_stock_themes(code)
            theme_heat_val = max((theme_heat.get(t, 0) for t in themes), default=0)

            # 簇热度(生命周期加权)
            cluster_max = max(
                (cluster_data.get(e["event_id"], {}).get("lifecycle_score", 0)
                 for e in data["events"]),
                default=0
            )
            # 生命周期系数取最高权重阶段
            lifecycle_weight = max(
                (cluster_data.get(e["event_id"], {}).get("lifecycle_weight", 0.5)
                 for e in data["events"]),
                default=0.5
            )
            lifecycle_score = cluster_max * lifecycle_weight

            # 龙头评分
            leader_score = self._load_leader_score(code)

            # V3 公式
            total = (event_score * 0.15 +
                     benefit_score * 0.20 +
                     market_score * 0.15 +
                     theme_heat_val * 0.15 +
                     cluster_max * 0.10 +
                     leader_score * 0.15 +
                     lifecycle_score * 0.10)

            top_events = sorted(data["events"], key=lambda x: -x.get("event_id", 0))[:3]
            results.append({
                "stock_code": code,
                "stock_name": data["stock_name"],
                "event_score": event_score,
                "benefit_score": benefit_score,
                "market_score": market_score,
                "theme_heat": round(theme_heat_val),
                "cluster_heat": round(cluster_max),
                "leader_score": round(leader_score),
                "lifecycle_weight": round(lifecycle_weight, 2),
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
            conn.execute("DELETE FROM recommendation_result")
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
                # 多维策略输出
                strategies = [
                    ("HOT", r["total_score"],
                     f"事件{r['event_score']}*15%+受益(分层){r['benefit_score']}*20%+"
                     f"市场{r['market_score']}*15%+热度{r['theme_heat']}*15%+"
                     f"簇{r['cluster_heat']}*10%+龙头{r['leader_score']}*15%+"
                     f"生命周期{r['lifecycle_weight']}*10%"),
                ]
                if r["theme_heat"] >= 50:
                    strategies.append(("THEME", r["theme_heat"], "热点题材"))
                if r["lifecycle_weight"] >= 0.8 and r["theme_heat"] < 30:
                    strategies.append(("LATENT", r["total_score"], "潜伏题材(早期+低热度)"))
                for stype, score, reason in strategies:
                    conn.execute("""
                        INSERT INTO recommendation_result
                            (stock_code, stock_name, strategy_type, rank_no, score, recommendation_reason)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (r["stock_code"], r["stock_name"], stype,
                          r["rank"], score, reason))
            conn.commit()
        print(f"  [评分] 已计算 {len(results)} 只股票的综合评分(V3)")

    def get_top_stocks(self, limit=20, strategy="HOT") -> list:
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

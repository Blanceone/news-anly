"""评分系统 — Phase 5

V1 公式：
  TotalScore = EventScore × 40% + BenefitScore × 60%

全量公式（预留）：
  TotalScore = 事件强度×20% + 受益程度×30% + 市场验证×20%
             + 财务质量×15% + 技术趋势×10% + 资金流向×5%
"""
import sqlite3
from collections import defaultdict
from datetime import datetime


class ScoringEngine:
    def __init__(self, db_path="news.db"):
        self.db_path = db_path
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
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT
                    es.stock_code, es.stock_name,
                    es.benefit_score, es.benefit_level,
                    e.event_score, e.event_type, e.importance,
                    e.sentiment, e.ai_summary, e.event_id
                FROM event_stock_mapping es
                JOIN event_analysis e ON es.event_id = e.event_id
                WHERE e.created_at > datetime(?, 'unixepoch')
            """, (since_ts,)).fetchall()
            return [dict(r) for r in rows]

    def _aggregate(self, rows: list) -> dict:
        stocks = defaultdict(lambda: {
            "stock_name": "",
            "event_scores": [],
            "benefit_scores": [],
            "events": [],
            "event_count": 0,
        })
        for r in rows:
            code = r["stock_code"]
            s = stocks[code]
            s["stock_name"] = r["stock_name"]
            s["event_scores"].append(r["event_score"] or 0)
            s["benefit_scores"].append(r["benefit_score"] or 0)
            s["events"].append({
                "event_id": r["event_id"],
                "type": r["event_type"],
                "importance": r["importance"],
                "sentiment": r["sentiment"],
                "summary": (r["ai_summary"] or "")[:80],
            })
            s["event_count"] += 1
        return dict(stocks)

    def _rank(self, stock_data: dict) -> list:
        results = []
        for code, data in stock_data.items():
            event_score = max(data["event_scores"]) if data["event_scores"] else 0
            benefit_score = max(data["benefit_scores"]) if data["benefit_scores"] else 0
            total = event_score * 0.4 + benefit_score * 0.6
            top_events = sorted(data["events"], key=lambda x: -x.get("event_id", 0))[:3]
            results.append({
                "stock_code": code,
                "stock_name": data["stock_name"],
                "event_score": event_score,
                "benefit_score": benefit_score,
                "market_score": 0,
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
                    f"事件{r['event_score']}分 *40% + 受益{r['benefit_score']}分 *60%",
                ))
            conn.commit()
        print(f"  [评分] 已计算 {len(results)} 只股票的评分")

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

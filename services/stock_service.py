"""股票关联服务 — Phase V4 (概念树驱动)

事件 → 股票映射：
1. concept_board 表：概念板块定义（东方财富爬取）
2. concept_stock_score 表：概念内排名（LLM分析+基本面评分）
3. event_stock_mapping 表：事件 → 关联股票（概念树匹配）

三层匹配机制:
  第1层: 精确匹配 — event.industry == concept_board.concept_name
  第2层: 关键词匹配 — event.keywords ∩ concept_board.keywords
  第3层: Embedding语义匹配 — TF-IDF 向量相似度
"""
import sqlite3
from datetime import datetime


class StockService:
    def __init__(self, db_path=None):
        from config import Config
        self.db_path = db_path or Config.STOCKS_DB
        self._init_table()

    def _init_table(self):
        from core.db_init import init_stocks_db
        init_stocks_db()

    # ─── 事件→股票匹配（概念树） ────────────────────────

    def match_event_to_stocks(self, event: dict) -> list:
        """根据事件的关键词/行业，通过概念树匹配受益股票"""
        keywords = event.get("keywords", [])
        industry = (event.get("industry") or "").strip()
        sub_industry = (event.get("sub_industry") or "").strip()

        matched_concepts = self._match_concepts(keywords, industry, sub_industry)
        if not matched_concepts:
            # 概念树可能尚未爬取，尝试 fallback
            return self._fallback_match(keywords, industry)

        return self._concepts_to_stocks(matched_concepts)

    def _match_concepts(self, keywords: list, industry: str,
                        sub_industry: str) -> list:
        """三层匹配: 精确 → 关键词 → Embedding"""
        matched = {}  # concept_id → {concept_name, match_score, match_method}

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            # 第1层: 精确匹配 industry → concept_name
            for text in (industry, sub_industry):
                if not text:
                    continue
                rows = conn.execute(
                    "SELECT concept_id, concept_name FROM concept_board "
                    "WHERE concept_name=? AND status='active'",
                    (text,)
                ).fetchall()
                for r in rows:
                    if r["concept_id"] not in matched:
                        matched[r["concept_id"]] = {
                            "concept_id": r["concept_id"],
                            "concept_name": r["concept_name"],
                            "match_score": 1.0,
                            "match_method": "exact",
                        }

            # 第2层: 关键词模糊匹配
            kw_lower = [k.lower() for k in keywords if len(k) >= 2]
            for kw in kw_lower:
                rows = conn.execute("""
                    SELECT concept_id, concept_name FROM concept_board
                    WHERE status='active'
                      AND (concept_name LIKE ? OR keywords LIKE ?)
                """, (f"%{kw}%", f"%{kw}%")).fetchall()
                for r in rows:
                    cid = r["concept_id"]
                    if cid not in matched:
                        matched[cid] = {
                            "concept_id": cid,
                            "concept_name": r["concept_name"],
                            "match_score": 0.8,
                            "match_method": "keyword",
                        }

        # 第3层: Embedding 语义匹配
        try:
            from services.embedding_service import get_embedding_service
            em = get_embedding_service()
            emb_matches = em.match_event(keywords, industry, sub_industry)
            for m in emb_matches:
                tname = m.get("theme_name", "")
                if not tname:
                    continue
                with sqlite3.connect(self.db_path) as conn:
                    rows = conn.execute(
                        "SELECT concept_id, concept_name FROM concept_board "
                        "WHERE concept_name=? AND status='active'",
                        (tname,)
                    ).fetchall()
                    for r in rows:
                        cid = r["concept_id"]
                        if cid not in matched:
                            matched[cid] = {
                                "concept_id": cid,
                                "concept_name": r["concept_name"],
                                "match_score": max(0.5, m.get("similarity", 0.5)),
                                "match_method": "embedding",
                            }
        except Exception:
            pass

        # 按匹配分数排序，取前5个概念
        results = sorted(matched.values(), key=lambda x: -x["match_score"])
        return results[:5]

    def _concepts_to_stocks(self, matched_concepts: list) -> list:
        """从匹配到的概念中获取TOP股票"""
        stocks = []
        seen = set()

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            for mc in matched_concepts:
                cid = mc["concept_id"]
                match_score = mc["match_score"]
                method = mc["match_method"]

                # 优先从 concept_stock_score 取TOP20（LLM分析后的排名）
                rows = conn.execute("""
                    SELECT stock_code, stock_name, total_score, rank_in_concept
                    FROM concept_stock_score
                    WHERE concept_id=?
                    ORDER BY rank_in_concept ASC
                    LIMIT 20
                """, (cid,)).fetchall()

                # fallback: concept_stock_member（仅成员列表，无排名）
                if not rows:
                    rows = conn.execute("""
                        SELECT stock_code, stock_name, 50 as total_score, 0 as rank_in_concept
                        FROM concept_stock_member
                        WHERE concept_id=?
                        ORDER BY rowid ASC
                        LIMIT 20
                    """, (cid,)).fetchall()

                for r in rows:
                    code = r["stock_code"]
                    if code in seen:
                        continue
                    seen.add(code)

                    concept_score = float(r["total_score"] or 50)
                    benefit_score = int(concept_score * match_score)

                    # benefit_type 由匹配方式决定
                    if method == "exact":
                        benefit_type = "DIRECT"
                    elif method == "keyword":
                        benefit_type = "INDIRECT"
                    else:
                        benefit_type = "SENTIMENT"

                    benefit_level = 1 if benefit_score >= 70 else (2 if benefit_score >= 40 else 3)

                    stocks.append({
                        "stock_code": code,
                        "stock_name": r["stock_name"],
                        "benefit_level": benefit_level,
                        "benefit_score": benefit_score,
                        "benefit_type": benefit_type,
                        "benefit_path": f"概念匹配({mc['concept_name']},{method})",
                        "_match_by": method,
                        "_concept_name": mc["concept_name"],
                        "_concept_id": cid,
                    })

        return stocks

    def _fallback_match(self, keywords: list, industry: str) -> list:
        """概念树为空时的 fallback: 从 theme_stock_mapping 匹配"""
        matched = set()
        all_text = f"{industry} {' '.join(keywords)}".lower()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT stock_code, stock_name, benefit_level,
                       benefit_reason, theme_name
                FROM theme_stock_mapping
            """).fetchall()
            for r in rows:
                reason = (r["benefit_reason"] or "").lower()
                theme = (r["theme_name"] or "").lower()
                if any(kw in all_text for kw in (theme, reason)):
                    matched.add((r["stock_code"], r["stock_name"],
                                 r["benefit_level"],
                                 r["benefit_reason"] or r["theme_name"]))

        return [{
            "stock_code": c, "stock_name": n,
            "benefit_level": l, "benefit_score": {1: 95, 2: 80, 3: 60}.get(l, 40),
            "benefit_type": "DIRECT" if l == 1 else "INDIRECT",
            "benefit_path": "fallback(旧主题库)",
            "benefit_reason": r,
            "_match_by": "fallback",
        } for c, n, l, r in matched]

    # ─── 事件股票处理 ──────────────────────────────────

    def _assign_benefit_type(self, stock: dict, match_source: str) -> str:
        btype = stock.get("benefit_type")
        if btype:
            return btype
        level = stock.get("benefit_level", 3)
        if match_source in ("exact", "keyword"):
            return "DIRECT" if level == 1 else "INDIRECT"
        if match_source == "embedding":
            return "INDIRECT"
        return "SENTIMENT"

    def _build_benefit_path(self, stock: dict, match_source: str) -> str:
        path = stock.get("benefit_path")
        if path:
            return path
        level = stock.get("benefit_level", 3)
        return f"概念匹配({match_source}, level={level})"

    def process_event_stocks(self, event_id: int, event: dict):
        """为事件创建股票关联"""
        matched = self.match_event_to_stocks(event)
        if not matched:
            return
        with sqlite3.connect(self.db_path) as conn:
            for stock in matched:
                src = stock.get("_match_by", "keyword")
                btype = self._assign_benefit_type(stock, src)
                bpath = self._build_benefit_path(stock, src)
                conn.execute("""
                    INSERT OR IGNORE INTO event_stock_mapping
                        (event_id, stock_code, stock_name, benefit_level, benefit_score,
                         benefit_type, benefit_path, match_reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (event_id, stock["stock_code"], stock["stock_name"],
                      stock.get("benefit_level", 2), stock.get("benefit_score", 60),
                      btype, bpath,
                      stock.get("benefit_reason", stock.get("_concept_name", ""))))
            conn.commit()

    # ─── 查询接口（保持不变） ──────────────────────────

    def get_top_stocks(self, hours=24, limit=20) -> list:
        from config import Config
        since = (datetime.now().timestamp() - hours * 3600)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT
                    es.stock_code,
                    es.stock_name,
                    AVG(es.benefit_score) as avg_benefit,
                    es.event_id
                FROM event_stock_mapping es
                GROUP BY es.stock_code, es.stock_name, es.event_id
            """).fetchall()
        event_ids = list({r["event_id"] for r in rows})
        event_map = {}
        if event_ids:
            placeholders = ",".join("?" for _ in event_ids)
            with sqlite3.connect(Config.NEWS_DB) as econn:
                econn.row_factory = sqlite3.Row
                erows = econn.execute(f"""
                    SELECT event_id, event_score, event_type, created_at
                    FROM event_analysis
                    WHERE event_id IN ({placeholders})
                      AND created_at > datetime(?, 'unixepoch')
                """, (*event_ids, since)).fetchall()
                event_map = {r["event_id"]: dict(r) for r in erows}
        stock_agg = {}
        for r in rows:
            e = event_map.get(r["event_id"])
            if e is None:
                continue
            code = r["stock_code"]
            if code not in stock_agg:
                stock_agg[code] = {
                    "stock_code": code,
                    "stock_name": r["stock_name"],
                    "benefit_scores": [],
                    "event_scores": [],
                    "event_types": set(),
                    "event_ids": set(),
                }
            sa = stock_agg[code]
            sa["benefit_scores"].append(r["avg_benefit"])
            sa["event_scores"].append(e["event_score"] or 0)
            if e["event_type"]:
                sa["event_types"].add(e["event_type"])
            sa["event_ids"].add(e["event_id"])
        result = []
        for code, sa in stock_agg.items():
            result.append({
                "stock_code": code,
                "stock_name": sa["stock_name"],
                "avg_benefit": sum(sa["benefit_scores"]) / len(sa["benefit_scores"]),
                "avg_event": sum(sa["event_scores"]) / len(sa["event_scores"]) if sa["event_scores"] else 0,
                "event_count": len(sa["event_ids"]),
                "event_types": ",".join(sorted(sa["event_types"])),
            })
        result.sort(key=lambda x: (-x["avg_benefit"], -x["avg_event"]))
        return result[:limit]

    def get_stock_events(self, stock_code: str, hours=72) -> list:
        from config import Config
        since = (datetime.now().timestamp() - hours * 3600)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT es.event_id, es.benefit_level, es.benefit_score, es.match_reason
                FROM event_stock_mapping es
                WHERE es.stock_code=?
            """, (stock_code,)).fetchall()
        event_ids = [r["event_id"] for r in rows]
        event_map = {}
        if event_ids:
            placeholders = ",".join("?" for _ in event_ids)
            with sqlite3.connect(Config.NEWS_DB) as econn:
                econn.row_factory = sqlite3.Row
                erows = econn.execute(f"""
                    SELECT event_id, event_type, industry, sentiment, importance,
                           event_score, ai_summary, created_at
                    FROM event_analysis
                    WHERE event_id IN ({placeholders})
                      AND created_at > datetime(?, 'unixepoch')
                """, (*event_ids, since)).fetchall()
                event_map = {r["event_id"]: dict(r) for r in erows}
        result = []
        for r in rows:
            e = event_map.get(r["event_id"])
            if e is None:
                continue
            result.append({
                "event_type": e["event_type"],
                "industry": e["industry"],
                "sentiment": e["sentiment"],
                "importance": e["importance"],
                "event_score": e["event_score"],
                "ai_summary": e["ai_summary"],
                "created_at": e["created_at"],
                "benefit_level": r["benefit_level"],
                "benefit_score": r["benefit_score"],
                "match_reason": r["match_reason"],
            })
        result.sort(key=lambda x: -(x["event_score"] or 0))
        return result

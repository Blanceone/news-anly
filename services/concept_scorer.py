"""概念内排名引擎 — Phase V4

基于 LLM 分析结果 + 基本面数据，为每个概念内的股票计算综合排名。

评分公式:
  total = relevance  * 0.30  (主营关联度, LLM输出)
        + valuation  * 0.20  (估值合理性, PE/PB)
        + quality    * 0.20  (公司质量, 市值/ROE/毛利率)
        + capability * 0.15  (真实能力, LLM判断)
        + chain      * 0.15  (产业链位置)

写入 concept_stock_score 表。
"""
import sqlite3
from datetime import datetime


# 产业链位置得分
_CHAIN_SCORES = {"upstream": 100, "midstream": 75, "downstream": 50}

# 重要性等级 → 能力基础分
_IMPORTANCE_BASE = {"S": 100, "A": 80, "B": 60, "C": 30}


class ConceptScorer:
    def __init__(self, db_path=None):
        from config import Config
        self.db_path = db_path or Config.STOCKS_DB
        self._init_tables()

    def _init_tables(self):
        from core.db_init import init_stocks_db
        init_stocks_db()

    # ─── 计算排名 ──────────────────────────────────────

    def score_concept(self, concept_id: str) -> list:
        """计算单个概念内的股票排名"""
        # 获取 LLM 分析
        analyses = self._get_analyses(concept_id)
        if not analyses:
            return []

        # 获取行业平均 PE（用于估值评分）
        concept = self._get_concept(concept_id)
        industry_avg_pe = 30.0
        if concept:
            # 取概念成分股中最常见行业的平均PE
            industry = self._get_dominant_industry(concept_id)
            if industry:
                industry_avg_pe = self._get_industry_avg_pe(industry)

        # 计算各维度得分
        scored = []
        for a in analyses:
            relevance = float(a.get("relevance_ratio", 0) or 0)
            relevance_score = min(100, relevance)

            valuation_score = self._calc_valuation_score(
                float(a.get("pe_ttm", 0) or 0),
                float(a.get("pb", 0) or 0),
                industry_avg_pe,
            )

            quality_score = self._calc_quality_score(
                float(a.get("total_mv", 0) or 0),
                float(a.get("roe", 0) or 0),
                float(a.get("gross_margin", 0) or 0),
            )

            capability_score = self._calc_capability_score(
                a.get("importance_level", "C"),
                int(a.get("is_real_capability", 0) or 0),
            )

            chain_score = _CHAIN_SCORES.get(
                str(a.get("chain_position", "midstream")).lower(), 50
            )

            total = (relevance_score * 0.30 +
                     valuation_score * 0.20 +
                     quality_score * 0.20 +
                     capability_score * 0.15 +
                     chain_score * 0.15)

            scored.append({
                "stock_code": a["stock_code"],
                "stock_name": a["stock_name"],
                "relevance_score": round(relevance_score, 1),
                "valuation_score": round(valuation_score, 1),
                "quality_score": round(quality_score, 1),
                "capability_score": round(capability_score, 1),
                "chain_score": round(chain_score, 1),
                "total_score": round(total, 1),
            })

        # 排序并赋排名
        scored.sort(key=lambda x: -x["total_score"])
        for i, s in enumerate(scored, 1):
            s["rank_in_concept"] = i

        # 写入 DB
        self._save_scores(concept_id, concept.get("name", "") if concept else "", scored)
        return scored

    def score_all(self) -> dict:
        """计算所有已分析概念的排名"""
        concepts = self._get_analyzed_concepts()
        if not concepts:
            print("  [概念排名] 无已分析的概念")
            return {"scored": 0}

        total_stocks = 0
        for concept in concepts:
            results = self.score_concept(concept["concept_id"])
            total_stocks += len(results)

        print(f"  [概念排名] 完成 {len(concepts)} 个概念, {total_stocks} 只股票排名")
        return {"scored": len(concepts), "stocks": total_stocks}

    # ─── 查询接口 ──────────────────────────────────────

    def get_top_stocks(self, concept_name: str, limit: int = 10) -> list:
        """获取某概念下排名靠前的股票"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM concept_stock_score
                WHERE concept_name=?
                ORDER BY rank_in_concept ASC
                LIMIT ?
            """, (concept_name, limit)).fetchall()
            return [dict(r) for r in rows]

    def get_top_stocks_by_id(self, concept_id: str, limit: int = 10) -> list:
        """获取某概念下排名靠前的股票(通过concept_id)"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM concept_stock_score
                WHERE concept_id=?
                ORDER BY rank_in_concept ASC
                LIMIT ?
            """, (concept_id, limit)).fetchall()
            return [dict(r) for r in rows]

    def get_stock_concepts(self, stock_code: str) -> list:
        """获取某股票所属的所有概念及其排名"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT css.*, sf.pe_ttm, sf.pb, sf.total_mv, sf.industry
                FROM concept_stock_score css
                LEFT JOIN stock_fundamentals sf ON css.stock_code = sf.stock_code
                WHERE css.stock_code=?
                ORDER BY css.total_score DESC
            """, (stock_code,)).fetchall()
            return [dict(r) for r in rows]

    def get_stock_score_in_concept(self, stock_code: str, concept_id: str) -> dict:
        """获取某股票在某概念中的评分"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("""
                SELECT * FROM concept_stock_score
                WHERE stock_code=? AND concept_id=?
            """, (stock_code, concept_id)).fetchone()
            return dict(row) if row else {}

    # ─── 评分维度计算 ──────────────────────────────────

    @staticmethod
    def _calc_valuation_score(pe: float, pb: float, industry_avg_pe: float) -> float:
        """估值评分: PE/PB 越合理分越高"""
        pe_score = 50.0
        if pe <= 0:
            # 亏损
            pe_score = 10.0
        elif pe > 0 and industry_avg_pe > 0:
            ratio = pe / industry_avg_pe
            if ratio <= 0.5:
                pe_score = 100.0  # 严重低估
            elif ratio <= 0.7:
                pe_score = 90.0
            elif ratio <= 1.0:
                pe_score = 80.0
            elif ratio <= 1.3:
                pe_score = 60.0
            elif ratio <= 2.0:
                pe_score = 40.0
            elif ratio <= 3.0:
                pe_score = 20.0
            else:
                pe_score = 10.0

        pb_score = 50.0
        if pb > 0:
            if pb < 1:
                pb_score = 90.0  # 破净，可能低估
            elif pb <= 3:
                pb_score = 70.0
            elif pb <= 8:
                pb_score = 50.0
            elif pb <= 15:
                pb_score = 30.0
            else:
                pb_score = 10.0
        elif pb < 0:
            pb_score = 10.0

        return pe_score * 0.6 + pb_score * 0.4

    @staticmethod
    def _calc_quality_score(market_cap: float, roe: float, margin: float) -> float:
        """公司质量评分: 市值大+ROE高+毛利率高 = 好公司"""
        # 市值评分 (亿元)
        mv_score = 0.0
        if market_cap >= 1000:
            mv_score = 100.0
        elif market_cap >= 500:
            mv_score = 80.0
        elif market_cap >= 100:
            mv_score = 60.0
        elif market_cap >= 30:
            mv_score = 40.0
        elif market_cap > 0:
            mv_score = 20.0

        # ROE 评分
        roe_score = 30.0
        if roe >= 20:
            roe_score = 100.0
        elif roe >= 15:
            roe_score = 85.0
        elif roe >= 10:
            roe_score = 70.0
        elif roe >= 5:
            roe_score = 50.0
        elif roe >= 0:
            roe_score = 30.0
        else:
            roe_score = 10.0

        # 毛利率评分
        margin_score = 40.0
        if margin >= 50:
            margin_score = 100.0
        elif margin >= 30:
            margin_score = 80.0
        elif margin >= 15:
            margin_score = 60.0
        elif margin >= 5:
            margin_score = 40.0
        elif margin >= 0:
            margin_score = 20.0

        return mv_score * 0.3 + roe_score * 0.4 + margin_score * 0.3

    @staticmethod
    def _calc_capability_score(importance: str, is_real: int) -> float:
        """真实能力评分: 重要性等级 × 是否真实"""
        base = _IMPORTANCE_BASE.get(importance.upper(), 30)
        if is_real:
            return base
        else:
            return base * 0.4  # 纯概念炒作打 6 折

    # ─── DB 操作 ──────────────────────────────────────

    def _save_scores(self, concept_id: str, concept_name: str, scored: list):
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            for s in scored:
                conn.execute("""
                    INSERT OR REPLACE INTO concept_stock_score
                        (concept_id, concept_name, stock_code, stock_name,
                         relevance_score, valuation_score, quality_score,
                         capability_score, chain_score, total_score,
                         rank_in_concept, scored_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (concept_id, concept_name, s["stock_code"], s["stock_name"],
                      s["relevance_score"], s["valuation_score"],
                      s["quality_score"], s["capability_score"],
                      s["chain_score"], s["total_score"],
                      s["rank_in_concept"], now))
            conn.commit()

    def _get_analyses(self, concept_id: str) -> list:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT csa.*, sf.pe_ttm, sf.pb, sf.total_mv,
                       sf.roe, sf.gross_margin, sf.industry
                FROM concept_stock_analysis csa
                LEFT JOIN stock_fundamentals sf ON csa.stock_code = sf.stock_code
                WHERE csa.concept_id=?
            """, (concept_id,)).fetchall()
            return [dict(r) for r in rows]

    def _get_concept(self, concept_id: str) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM concept_board WHERE concept_id=?",
                (concept_id,)
            ).fetchone()
            return dict(row) if row else None

    def _get_analyzed_concepts(self) -> list:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT DISTINCT concept_id, concept_name
                FROM concept_stock_analysis
            """).fetchall()
            return [dict(r) for r in rows]

    def _get_dominant_industry(self, concept_id: str) -> str:
        """获取概念成分股中最常见的行业"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute("""
                    SELECT sf.industry, COUNT(*) as cnt
                    FROM concept_stock_member csm
                    JOIN stock_fundamentals sf ON csm.stock_code = sf.stock_code
                    WHERE csm.concept_id=? AND sf.industry != ''
                    GROUP BY sf.industry
                    ORDER BY cnt DESC
                    LIMIT 1
                """, (concept_id,)).fetchone()
                return row[0] if row else ""
        except Exception:
            return ""

    def _get_industry_avg_pe(self, industry: str) -> float:
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute("""
                    SELECT AVG(pe_ttm) FROM stock_fundamentals
                    WHERE industry=? AND pe_ttm > 0 AND pe_ttm < 1000
                """, (industry,)).fetchone()
                return float(row[0]) if row and row[0] else 30.0
        except Exception:
            return 30.0

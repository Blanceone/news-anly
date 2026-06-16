"""LLM 概念分析服务 — Phase V4

对每个概念板块的成分股进行 LLM 分析，确定:
  - 主营业务关联度 (relevance_ratio, 0-100)
  - 产业链位置 (chain_position: upstream/midstream/downstream)
  - 重要性等级 (importance_level: S/A/B/C)
  - 是否具备真实能力 (is_real_capability: 0/1)

写入 concept_stock_analysis 表。
"""
import json
import re
import sqlite3
import time
from datetime import datetime, timedelta


_SYSTEM_PROMPT = """你是一名资深A股行业分析师。你的任务是分析一个概念板块的成分股，评估每只股票与该概念的关联程度。

分析维度:
1. relevance_ratio (0-100): 该股票主营业务与概念概念的关联度。100=核心业务完全匹配，50=部分相关，10=弱关联/跟风
2. chain_position: 在产业链中的位置。upstream=上游(原材料/核心零部件)，midstream=中游(制造/集成)，downstream=下游(应用/终端)
3. importance_level: 重要性等级。S=绝对龙头/不可替代，A=核心参与者，B=一般参与者，C=边缘/跟风
4. is_real_capability: 是否有真实业务能力(非纯概念炒作)。true=有实际营收/技术/产品，false=仅蹭概念

请严格按照以下JSON格式输出，不要输出任何其他内容:
```json
[
  {
    "stock_code": "代码",
    "relevance_ratio": 85,
    "chain_position": "upstream",
    "importance_level": "A",
    "is_real_capability": true,
    "reason": "一句话理由"
  }
]
```

注意:
- 必须为列表中的每只股票都输出分析结果
- relevance_ratio 要基于公司实际业务判断，不要仅看名称
- 市值大不一定重要性高，要看与概念的实际关联
- 如果某只股票确实与概念无关，relevance_ratio 给低分即可"""


class ConceptAnalyzer:
    MAX_STOCKS_PER_CONCEPT = 80  # 每次LLM分析最多80只股票

    def __init__(self, db_path=None):
        from config import Config
        self.db_path = db_path or Config.STOCKS_DB
        self._init_tables()
        from services.llm_client import LLMClient
        self.llm = LLMClient()

    def _init_tables(self):
        from core.db_init import init_stocks_db
        init_stocks_db()

    # ─── 分析单个概念 ──────────────────────────────────

    def analyze_concept(self, concept_id: str) -> int:
        """分析单个概念的所有成分股"""
        if not self.llm.available:
            print(f"  [概念分析] LLM 不可用，跳过分析")
            return 0

        # 获取概念信息
        concept = self._get_concept(concept_id)
        if not concept:
            return 0

        # 获取成分股 + 基本面
        stocks = self._get_stocks_with_fundamentals(concept_id)
        if not stocks:
            print(f"  [概念分析] '{concept['name']}' 无成分股数据")
            return 0

        # 截断过多股票（按市值排序取前N只）
        if len(stocks) > self.MAX_STOCKS_PER_CONCEPT:
            stocks = stocks[:self.MAX_STOCKS_PER_CONCEPT]

        # 构建 Prompt → LLM → 解析
        prompt = self._build_prompt(concept, stocks)
        raw = self.llm.chat(_SYSTEM_PROMPT, prompt, temperature=0.1)
        results = self._parse_response(raw, stocks)

        if not results:
            print(f"  [概念分析] '{concept['name']}' LLM 输出解析失败")
            return 0

        # 写入 DB
        self._save_results(concept_id, concept["name"], results)
        return len(results)

    # ─── 增量分析 ──────────────────────────────────────

    def analyze_changed(self) -> dict:
        """仅分析新增/变更的概念"""
        if not self.llm.available:
            return {"skipped": True, "reason": "LLM不可用"}

        # 查找需要分析的概念:
        # 1. 完全没有分析记录的
        # 2. 成分股更新后未重新分析的
        concepts_to_analyze = self._find_unanalyzed_concepts()

        if not concepts_to_analyze:
            print("  [概念分析] 所有概念已有分析结果，无需更新")
            return {"analyzed": 0, "concepts": []}

        print(f"  [概念分析] 需要分析 {len(concepts_to_analyze)} 个概念...")
        results = {"analyzed": 0, "concepts": [], "failed": 0}

        for i, concept in enumerate(concepts_to_analyze):
            try:
                count = self.analyze_concept(concept["concept_id"])
                if count > 0:
                    results["analyzed"] += count
                    results["concepts"].append(concept["concept_name"])
                else:
                    results["failed"] += 1
            except Exception as e:
                print(f"  [概念分析] '{concept['concept_name']}' 分析失败: {e}")
                results["failed"] += 1

            # 限流: 每分钟约10次
            if i < len(concepts_to_analyze) - 1:
                time.sleep(6)

            if (i + 1) % 10 == 0:
                print(f"  [概念分析] 进度: {i+1}/{len(concepts_to_analyze)}")

        print(f"  [概念分析] 完成: {results['analyzed']} 只股票, "
              f"{len(results['concepts'])} 个概念, {results['failed']} 失败")
        return results

    def analyze_all(self, force: bool = False) -> dict:
        """分析所有活跃概念"""
        if not self.llm.available:
            return {"skipped": True, "reason": "LLM不可用"}

        concepts = self._get_all_active_concepts()
        if not concepts:
            return {"analyzed": 0}

        if not force:
            # 过滤已有分析结果的概念
            concepts = [c for c in concepts if not self._has_analysis(c["concept_id"])]

        print(f"  [概念分析] 分析 {len(concepts)} 个概念...")
        results = {"analyzed": 0, "concepts": [], "failed": 0}

        for i, concept in enumerate(concepts):
            try:
                count = self.analyze_concept(concept["concept_id"])
                if count > 0:
                    results["analyzed"] += count
                    results["concepts"].append(concept["concept_name"])
                else:
                    results["failed"] += 1
            except Exception as e:
                print(f"  [概念分析] '{concept['concept_name']}' 失败: {e}")
                results["failed"] += 1
            if i < len(concepts) - 1:
                time.sleep(6)
            if (i + 1) % 10 == 0:
                print(f"  [概念分析] 进度: {i+1}/{len(concepts)}")

        return results

    # ─── 查询接口 ──────────────────────────────────────

    def get_analysis(self, concept_id: str) -> list:
        """获取某概念的 LLM 分析结果"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM concept_stock_analysis
                WHERE concept_id=?
                ORDER BY relevance_ratio DESC
            """, (concept_id,)).fetchall()
            return [dict(r) for r in rows]

    def get_stock_analysis(self, stock_code: str) -> list:
        """获取某股票在所有概念中的分析结果"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM concept_stock_analysis
                WHERE stock_code=?
                ORDER BY relevance_ratio DESC
            """, (stock_code,)).fetchall()
            return [dict(r) for r in rows]

    # ─── Prompt 构建 ──────────────────────────────────

    def _build_prompt(self, concept: dict, stocks: list) -> str:
        lines = [
            f"概念板块: {concept['name']}",
            f"概念描述: {concept.get('keywords', '')}",
            f"成分股数量: {len(stocks)} 只",
            "",
            "成分股列表（含基本面数据）:",
            "-" * 60,
        ]
        for s in stocks:
            info_parts = [f"代码: {s['stock_code']}", f"名称: {s['stock_name']}"]
            if s.get("industry"):
                info_parts.append(f"行业: {s['industry']}")
            if s.get("total_mv") and s["total_mv"] > 0:
                info_parts.append(f"市值: {s['total_mv']:.1f}亿")
            if s.get("pe_ttm") and s["pe_ttm"] != 0:
                info_parts.append(f"PE: {s['pe_ttm']:.1f}")
            if s.get("company_business"):
                info_parts.append(f"主营: {s['company_business'][:100]}")
            lines.append("  " + " | ".join(info_parts))

        lines.append("")
        lines.append(f"请为以上 {len(stocks)} 只股票逐一分析，输出JSON数组。")
        return "\n".join(lines)

    # ─── LLM 输出解析 ─────────────────────────────────

    def _parse_response(self, raw: str, stocks: list) -> list:
        if not raw:
            return []

        # 提取 JSON 数组
        json_str = self._extract_json(raw)
        if not json_str:
            return []

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return []

        if not isinstance(data, list):
            return []

        # 构建 stock_code 集合用于匹配
        stock_codes = {s["stock_code"] for s in stocks}
        stock_name_to_code = {s["stock_name"]: s["stock_code"] for s in stocks}

        results = []
        valid_levels = {"S", "A", "B", "C"}
        valid_positions = {"upstream", "midstream", "downstream"}

        for item in data:
            if not isinstance(item, dict):
                continue

            # 匹配股票代码
            code = str(item.get("stock_code", "")).strip()
            # 去掉可能的后缀
            code = re.sub(r'\.(SZ|SH|BJ)$', '', code, flags=re.IGNORECASE)
            if code not in stock_codes:
                # 尝试通过名称匹配
                name = str(item.get("stock_name", ""))
                code = stock_name_to_code.get(name, "")
            if not code or code not in stock_codes:
                continue

            # 校验并规范化字段
            relevance = item.get("relevance_ratio", 50)
            try:
                relevance = max(0, min(100, float(relevance)))
            except (TypeError, ValueError):
                relevance = 50

            position = str(item.get("chain_position", "midstream")).lower()
            if position not in valid_positions:
                position = "midstream"

            level = str(item.get("importance_level", "C")).upper()
            if level not in valid_levels:
                level = "C"

            is_real = item.get("is_real_capability", False)
            if isinstance(is_real, str):
                is_real = is_real.lower() in ("true", "yes", "1")
            else:
                is_real = bool(is_real)

            reason = str(item.get("reason", ""))[:200]

            # 查找股票名称
            stock_name = ""
            for s in stocks:
                if s["stock_code"] == code:
                    stock_name = s["stock_name"]
                    break

            results.append({
                "stock_code": code,
                "stock_name": stock_name,
                "relevance_ratio": relevance,
                "chain_position": position,
                "importance_level": level,
                "is_real_capability": 1 if is_real else 0,
                "analysis_reason": reason,
            })

        return results

    @staticmethod
    def _extract_json(text: str) -> str:
        """从 LLM 输出中提取 JSON 数组"""
        # 尝试找 ```json ... ``` 代码块
        m = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', text, re.DOTALL)
        if m:
            return m.group(1)
        # 直接找 [...]
        m = re.search(r'\[.*\]', text, re.DOTALL)
        if m:
            return m.group(0)
        return ""

    # ─── DB 操作 ──────────────────────────────────────

    def _save_results(self, concept_id: str, concept_name: str, results: list):
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            for r in results:
                conn.execute("""
                    INSERT OR REPLACE INTO concept_stock_analysis
                        (concept_id, concept_name, stock_code, stock_name,
                         relevance_ratio, chain_position, importance_level,
                         is_real_capability, analysis_reason, llm_model, analyzed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (concept_id, concept_name, r["stock_code"], r["stock_name"],
                      r["relevance_ratio"], r["chain_position"],
                      r["importance_level"], r["is_real_capability"],
                      r["analysis_reason"], self.llm.model, now))
            conn.commit()

    def _get_concept(self, concept_id: str) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM concept_board WHERE concept_id=?",
                (concept_id,)
            ).fetchone()
            return dict(row) if row else None

    def _get_stocks_with_fundamentals(self, concept_id: str) -> list:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT csm.stock_code, csm.stock_name,
                       sf.industry, sf.pe_ttm, sf.pb, sf.total_mv,
                       sf.company_business
                FROM concept_stock_member csm
                LEFT JOIN stock_fundamentals sf ON csm.stock_code = sf.stock_code
                WHERE csm.concept_id=?
                ORDER BY sf.total_mv DESC
            """, (concept_id,)).fetchall()
            return [dict(r) for r in rows]

    def _find_unanalyzed_concepts(self) -> list:
        """查找需要分析的概念（无分析记录 或 分析过期）"""
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            # 无分析记录的概念
            rows = conn.execute("""
                SELECT cb.concept_id, cb.concept_name
                FROM concept_board cb
                LEFT JOIN concept_stock_analysis csa ON cb.concept_id = csa.concept_id
                WHERE csa.id IS NULL AND cb.status='active' AND cb.stock_count > 0
            """).fetchall()
            result = [dict(r) for r in rows]

            # 分析过期的概念
            rows2 = conn.execute("""
                SELECT DISTINCT cb.concept_id, cb.concept_name
                FROM concept_board cb
                JOIN concept_stock_analysis csa ON cb.concept_id = csa.concept_id
                WHERE cb.status='active'
                GROUP BY cb.concept_id
                HAVING MAX(csa.analyzed_at) < ?
            """, (cutoff,)).fetchall()
            for r in rows2:
                if r["concept_id"] not in {x["concept_id"] for x in result}:
                    result.append(dict(r))
            return result

    def _get_all_active_concepts(self) -> list:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT concept_id, concept_name FROM concept_board WHERE status='active' AND stock_count > 0"
            ).fetchall()
            return [dict(r) for r in rows]

    def _has_analysis(self, concept_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM concept_stock_analysis WHERE concept_id=?",
                (concept_id,)
            ).fetchone()
            return row[0] > 0 if row else False

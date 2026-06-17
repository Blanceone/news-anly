"""AI 事件抽取与概念归一化服务

严格按 V3 Final Spec 第3章 Prompt 设计:
  3.1 事件抽取 Prompt: 从新闻中提取结构化事件 + potential_concepts
  3.2 概念归一化 Prompt: 将离散概念映射到标准词典或标记为新概念

流程 (Spec 4.2):
  news → LLM事件抽取 → 入库event_analysis → LLM概念归一化 → 更新词典+激活候选
"""
import json
import re
import sqlite3
from datetime import datetime

from core.llm_client import LLMClient
from config import Config


# ──────────────────────────────────────────────
# Spec 3.1: 事件抽取 Prompt
# ──────────────────────────────────────────────

EVENT_EXTRACTION_SYSTEM = (
    "你是一位资深的A股财经分析师和产业研究员。你的任务是从提供的文本中精准提取结构化的事件信息，"
    "并识别出可能引发A股市场概念炒作的产业关键词。你只返回JSON格式数据，不要任何解释。"
)

EVENT_EXTRACTION_USER = """请分析以下文本并提取事件信息：
文本内容：{input_text}
请严格按照以下JSON Schema返回结果：
{{
  "event_type": "枚举值: 政策发布/技术突破/行业数据/公司公告/海外映射",
  "summary": "一句话概括事件核心内容(不超过50字)",
  "sentiment": "枚举值: 利好/利空/中性",
  "entities": ["涉及的实体，如公司名、政府机构名、产品名"],
  "potential_concepts": ["提取文本中可能引发炒作的原始概念词，如'低空经济'、'固态电池'、'英伟达供应链'。尽可能具体，数量1-3个。"]
}}"""

# ──────────────────────────────────────────────
# Spec 3.2: 概念归一化 Prompt
# ──────────────────────────────────────────────

CONCEPT_NORMALIZATION_SYSTEM = (
    "你是一位金融NLP数据清洗专家。你的任务是将输入的离散概念关键词，与提供的标准概念词典进行语义匹配。"
    "匹配规则：如果关键词是词典中某概念的别名或同义词，则映射到该标准概念；"
    "如果找不到匹配项，则标记为新概念。只返回JSON格式数组。"
)

CONCEPT_NORMALIZATION_USER = """当前标准概念词典（standard_name: aliases）：
{dictionary_json}
需要归一化的原始关键词列表：
{raw_concepts_list}
请对每一个原始关键词进行处理，返回如下JSON数组：
[
  {{
    "raw_keyword": "原始关键词",
    "standard_concept": "匹配到的标准概念名，若无则填'UNKNOWN'",
    "is_new": true
  }}
]"""


class EventService:
    def __init__(self, news_db=None, concept_db=None):
        self.llm = LLMClient()
        self.news_db = news_db or Config.NEWS_DB
        self.concept_db = concept_db or Config.CONCEPT_DB

    # ──────────────────────────────────────────
    # 核心: Spec 4.2 process_news 流程
    # ──────────────────────────────────────────

    def process_news(self, news_text: str, news_id: str) -> dict:
        """处理单条新闻: 事件抽取 → 入库 → 概念归一化 → 更新词典"""
        # 1. 调用LLM进行事件抽取 (Spec 3.1)
        user_prompt = EVENT_EXTRACTION_USER.format(input_text=news_text[:2000])
        raw_response = self.llm.chat(EVENT_EXTRACTION_SYSTEM, user_prompt, temperature=0.1)
        event_data = self._parse_json_object(raw_response)

        if not event_data:
            event_data = {
                "event_type": "公司公告",
                "summary": "",
                "sentiment": "中性",
                "entities": [],
                "potential_concepts": [],
            }

        # 2. 入库 event_analysis 表
        event_id = self._save_event(news_id, event_data)
        event_data["_event_id"] = event_id

        # 3. 调用LLM进行概念归一化 (Spec 3.2)
        potential_concepts = event_data.get("potential_concepts", [])
        if potential_concepts and self.llm.available:
            dict_json = self._get_concept_dictionary()
            norm_prompt = CONCEPT_NORMALIZATION_USER.format(
                dictionary_json=json.dumps(dict_json, ensure_ascii=False),
                raw_concepts_list=json.dumps(potential_concepts, ensure_ascii=False),
            )
            norm_response = self.llm.chat(
                CONCEPT_NORMALIZATION_SYSTEM, norm_prompt, temperature=0.0
            )
            norm_data = self._parse_json_array(norm_response)
            # 4. 处理归一化结果：更新词典、激活概念候选池
            if norm_data:
                event_data["_normalized"] = self._process_normalized_concepts(
                    norm_data, event_id
                )

        # 更新 news 表标记已处理
        self._mark_processed(news_id, event_data)
        return event_data

    def process_news_item(self, news_item: dict) -> dict:
        """兼容入口: 处理 news_item dict"""
        text = f"{news_item.get('title', '')}\n{news_item.get('content', '')}"
        result = self.process_news(text, news_item["id"])
        return {
            "event_type": result.get("event_type", ""),
            "sentiment": result.get("sentiment", ""),
            "summary": result.get("summary", ""),
            "entities": result.get("entities", []),
            "potential_concepts": result.get("potential_concepts", []),
            "_event_id": result.get("_event_id"),
        }

    # ──────────────────────────────────────────
    # 数据持久化
    # ──────────────────────────────────────────

    def _save_event(self, news_id: str, event_data: dict) -> int:
        """写入 event_analysis 表，返回 event_id"""
        with sqlite3.connect(self.news_db) as conn:
            cursor = conn.execute("""
                INSERT INTO event_analysis
                    (news_id, event_type, entities, summary, sentiment, raw_concepts, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                news_id,
                event_data.get("event_type", ""),
                json.dumps(event_data.get("entities", []), ensure_ascii=False),
                event_data.get("summary", ""),
                event_data.get("sentiment", ""),
                json.dumps(event_data.get("potential_concepts", []), ensure_ascii=False),
                datetime.now().isoformat(),
            ))
            event_id = cursor.lastrowid
            conn.commit()
        return event_id

    def _mark_processed(self, news_id: str, event_data: dict):
        """更新 news 表: 标记 is_processed=1, 写入 sentiment/category"""
        sentiment_map = {"利好": "positive", "利空": "negative", "中性": "neutral"}
        sentiment = sentiment_map.get(event_data.get("sentiment", ""), "neutral")
        with sqlite3.connect(self.news_db) as conn:
            conn.execute("""
                UPDATE news SET is_processed=1, analyzed=1, sentiment=?, category=?,
                       ai_analysis=?, updated_at=?
                WHERE id=?
            """, (
                sentiment,
                event_data.get("event_type", ""),
                event_data.get("summary", ""),
                datetime.now().isoformat(),
                news_id,
            ))
            conn.commit()

    # ──────────────────────────────────────────
    # 概念词典操作
    # ──────────────────────────────────────────

    def _get_concept_dictionary(self) -> list:
        """从 concept_dictionary 表获取标准概念列表"""
        try:
            with sqlite3.connect(self.concept_db) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT standard_name, aliases FROM concept_dictionary WHERE status='active'"
                ).fetchall()
                return [{"standard_name": r["standard_name"],
                         "aliases": r["aliases"]} for r in rows]
        except Exception:
            return []

    def _process_normalized_concepts(self, norm_data: list, event_id: int) -> list:
        """处理归一化结果: 新概念加入词典, 所有概念激活候选池"""
        results = []
        with sqlite3.connect(self.concept_db) as conn:
            for item in norm_data:
                raw = item.get("raw_keyword", "").strip()
                standard = item.get("standard_concept", "UNKNOWN").strip()
                is_new = item.get("is_new", False)

                if not raw:
                    continue

                # 新概念 → 加入词典
                if is_new:
                    try:
                        conn.execute("""
                            INSERT OR IGNORE INTO concept_dictionary
                                (standard_name, aliases, category, status)
                            VALUES (?, ?, 'unknown', 'active')
                        """, (standard, json.dumps([raw], ensure_ascii=False)))
                    except Exception:
                        pass

                # 激活概念候选池: 加入 concept_candidate
                conn.execute("""
                    INSERT OR IGNORE INTO concept_candidate
                        (standard_name, status, created_at, mention_count, last_mention_date)
                    VALUES (?, 'candidate', ?, 0, ?)
                """, (standard, datetime.now().isoformat(),
                      datetime.now().strftime("%Y-%m-%d")))

                # 关联事件
                concept_row = conn.execute(
                    "SELECT id FROM concept_candidate WHERE standard_name=?",
                    (standard,)
                ).fetchone()
                if concept_row:
                    concept_id = concept_row[0]
                    trade_date = datetime.now().strftime("%Y-%m-%d")
                    conn.execute("""
                        INSERT OR IGNORE INTO concept_event
                            (concept_id, event_id, trade_date)
                        VALUES (?, ?, ?)
                    """, (concept_id, event_id, trade_date))

                    # 递增提及计数
                    conn.execute("""
                        UPDATE concept_candidate
                        SET mention_count = mention_count + 1,
                            last_mention_date = ?
                        WHERE id = ?
                    """, (trade_date, concept_id))

                results.append({
                    "raw_keyword": raw,
                    "standard_concept": standard,
                    "is_new": is_new,
                })
            conn.commit()
        return results

    # ──────────────────────────────────────────
    # JSON 解析
    # ──────────────────────────────────────────

    def _parse_json_object(self, text: str) -> dict:
        if not text:
            return None
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return None

    def _parse_json_array(self, text: str) -> list:
        if not text:
            return []
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return []

    # ──────────────────────────────────────────
    # 查询方法
    # ──────────────────────────────────────────

    def get_recent_events(self, hours=24, limit=50) -> list:
        """获取最近事件"""
        since = (datetime.now().timestamp() - hours * 3600)
        with sqlite3.connect(self.news_db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT e.*, n.title, n.source_name, n.created_at
                FROM event_analysis e
                JOIN news n ON e.news_id = n.id
                WHERE e.created_at > datetime(?, 'unixepoch')
                ORDER BY e.created_at DESC
                LIMIT ?
            """, (since, limit)).fetchall()
            return [dict(r) for r in rows]

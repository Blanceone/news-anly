"""AI 事件识别服务

按 PRD #AI事件识别Prompt设计规范 实现的结构化事件抽取。
AI 只负责：事件分类 / 情绪分析 / 实体识别 / 行业识别 / 金额提取
AI 禁止：推荐股票 / 买卖建议 / 预测涨跌
"""
import json
import re
import sqlite3
from datetime import datetime

from config import Config
from services.llm_client import LLMClient

SYSTEM_PROMPT = """你是一名专业财经事件抽取助手。

你的任务：从新闻中提取结构化事件信息。

禁止：
- 推荐股票
- 分析买卖
- 判断股价

必须：
- 输出标准JSON
- 不输出解释
- 不输出Markdown

事件类型必须从以下集合中选择：
ORDER（订单类）、EARNINGS（业绩类）、TECHNOLOGY（技术突破）、
POLICY（政策催化）、MNA（并购重组）、CAPITAL（股东行为）、
RISK（风险事件）、OTHER（其他）

重要性等级：S（重大事件）、A（重大催化）、B（普通利好）、C（影响较小）"""

USER_PROMPT_TEMPLATE = """请分析以下财经新闻：

标题：
{title}

正文：
{content}

按照指定JSON格式返回结果。"""


class EventService:
    def __init__(self, db_path="news.db"):
        self.llm = LLMClient()
        self.db_path = db_path
        self._init_table()

    def _init_table(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS event_analysis (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_type TEXT,
                    source_id TEXT,
                    event_type TEXT,
                    event_subtype TEXT,
                    industry TEXT,
                    sub_industry TEXT,
                    sentiment TEXT,
                    importance TEXT,
                    novelty_score INTEGER,
                    event_score INTEGER,
                    entities_json TEXT,
                    amount REAL,
                    amount_unit TEXT,
                    keywords_json TEXT,
                    ai_summary TEXT,
                    reason TEXT,
                    raw_response TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def _compute_event_score(self, importance: str, novelty: int) -> int:
        base = {"S": 100, "A": 80, "B": 60, "C": 40}.get(importance, 40)
        novelty_factor = novelty / 100.0
        return int(base * 0.7 + novelty * 0.3)

    def extract(self, title: str, content: str) -> dict:
        if not self.llm.available:
            return self._fallback()

        user_prompt = USER_PROMPT_TEMPLATE.format(title=title, content=content[:1000])

        try:
            raw = self.llm.chat(SYSTEM_PROMPT, user_prompt, temperature=0.1)
            parsed = self._parse_json(raw)
            if parsed:
                return self._validate(parsed)
        except Exception:
            pass

        return self._fallback()

    def _parse_json(self, text: str) -> dict:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return None

    def _validate(self, data: dict) -> dict:
        valid_types = {"ORDER", "EARNINGS", "TECHNOLOGY", "POLICY", "MNA", "CAPITAL", "RISK", "OTHER"}
        valid_importance = {"S", "A", "B", "C"}
        valid_sentiment = {"positive", "negative", "neutral"}

        event_type = str(data.get("event_type", "OTHER")).upper()
        if event_type not in valid_types:
            event_type = "OTHER"

        importance = str(data.get("importance", "C")).upper()
        if importance not in valid_importance:
            importance = "C"

        sentiment = str(data.get("sentiment", "neutral")).lower()
        if sentiment not in valid_sentiment:
            sentiment = "neutral"

        novelty = int(data.get("novelty_score", 0) or 0)
        novelty = max(0, min(100, novelty))

        return {
            "event_type": event_type,
            "event_subtype": str(data.get("event_subtype", "")),
            "industry": str(data.get("industry", "")),
            "sub_industry": str(data.get("sub_industry", "")),
            "sentiment": sentiment,
            "importance": importance,
            "novelty_score": novelty,
            "event_score": self._compute_event_score(importance, novelty),
            "entities": data.get("entities", []),
            "amount": float(data.get("amount", 0) or 0),
            "amount_unit": str(data.get("amount_unit", "")),
            "keywords": data.get("keywords", []),
            "ai_summary": str(data.get("summary", "")),
            "reason": str(data.get("reason", "")),
        }

    def _fallback(self) -> dict:
        return {
            "event_type": "OTHER",
            "event_subtype": "",
            "industry": "",
            "sub_industry": "",
            "sentiment": "neutral",
            "importance": "C",
            "novelty_score": 0,
            "event_score": 0,
            "entities": [],
            "amount": 0.0,
            "amount_unit": "",
            "keywords": [],
            "ai_summary": "",
            "reason": "",
        }

    def process_news_item(self, news_item: dict) -> dict:
        result = self.extract(news_item["title"], news_item.get("content", ""))
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO event_analysis
                    (source_type, source_id, event_type, event_subtype,
                     industry, sub_industry, sentiment, importance,
                     novelty_score, event_score, entities_json, amount, amount_unit,
                     keywords_json, ai_summary, reason, raw_response)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "news",
                news_item["id"],
                result["event_type"],
                result["event_subtype"],
                result["industry"],
                result["sub_industry"],
                result["sentiment"],
                result["importance"],
                result["novelty_score"],
                result["event_score"],
                json.dumps(result["entities"], ensure_ascii=False),
                result["amount"],
                result["amount_unit"],
                json.dumps(result["keywords"], ensure_ascii=False),
                result["ai_summary"],
                result["reason"],
                "",
            ))
            conn.execute("""
                UPDATE news SET sentiment=?, category=?, impact=?, ai_analysis=?, updated_at=?
                WHERE id=?
            """, (
                result["sentiment"],
                result["event_type"],
                result["event_score"],
                result["ai_summary"],
                datetime.now().isoformat(),
                news_item["id"],
            ))
        return result

    def get_recent_events(self, hours=24, limit=50) -> list:
        since = (datetime.now().timestamp() - hours * 3600)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT e.*, n.title, n.source_name, n.created_at
                FROM event_analysis e
                JOIN news n ON e.source_id = n.id
                WHERE e.created_at > datetime(?, 'unixepoch')
                ORDER BY e.event_score DESC, e.created_at DESC
                LIMIT ?
            """, (since, limit)).fetchall()
            return [dict(r) for r in rows]

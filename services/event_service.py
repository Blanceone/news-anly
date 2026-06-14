"""AI 事件识别服务

按 PRD #AI事件识别Prompt设计规范 实现的结构化事件抽取。
AI 只负责：事件分类 / 情绪分析 / 实体识别 / 行业识别 / 金额提取
AI 禁止：推荐股票 / 买卖建议 / 预测涨跌
"""
import json
import re
import sqlite3
from datetime import datetime

from services.llm_client import LLMClient
from services.theme_discovery import ThemeDiscovery
from services.event_cluster import EventClustering

EVENT_TYPE_DEFS = """
事件类型（必填，选一个）：
- ORDER 订单类：重大订单、长期订单、海外订单、中标项目、战略合作
- EARNINGS 业绩类：业绩预增、业绩预减、业绩快报、年报、季报
- TECHNOLOGY 技术突破：技术突破、新工艺、新产品、技术认证、专利
- POLICY 政策催化：国家政策、地方政策、行业规范、补贴
- MNA 并购重组：收购、兼并、资产重组、借壳
- CAPITAL 股东行为：增持、减持、回购、股权激励
- RISK 风险事件：处罚、诉讼、问询函、安全事故、退市风险
- OTHER 其他：不属于以上类别的事件

情绪（必填，三选一）：
- positive 正面利好：订单、技术突破、业绩增长、政策支持
- negative 负面利空：减持、处罚、诉讼、亏损
- neutral 中性：日常事项、召开会议、发布公告

重要性（必填，四选一）：
- S 重大事件：国家级产业政策、千亿级项目、行业颠覆性技术
- A 重大催化：重大订单、核心技术突破、超预期业绩
- B 普通利好：一般合作、产品发布
- C 影响较小：常规公告、日常事项

novelty_score（必填，0-100）：
- 已反复报道=10-30，普通更新=40-60，首次披露=70-90，行业首创=90-100
"""

SYSTEM_PROMPT = f"""你是一名专业财经事件抽取助手。

你的任务：从新闻中提取结构化事件信息。

禁止：
- 推荐股票
- 分析买卖
- 判断股价

必须：
- 输出标准JSON（不输出解释，不输出Markdown）
- event_type / sentiment / importance / novelty_score 为必填

{EVENT_TYPE_DEFS}

输出JSON格式：
{{
  "event_type": "ORDER|EARNINGS|TECHNOLOGY|POLICY|MNA|CAPITAL|RISK|OTHER",
  "event_subtype": "具体子类别",
  "industry": "所属行业",
  "sub_industry": "细分行业",
  "sentiment": "positive|negative|neutral",
  "importance": "S|A|B|C",
  "novelty_score": 85,
  "entities": [{{"type": "company|stock|technology|industry", "name": "实体名称"}}],
  "amount": 金额数字,
  "amount_unit": "亿元|万元|元",
  "keywords": ["关键词1", "关键词2"],
  "summary": "一句话总结事件",
  "reason": "分类理由"
}}"""

USER_PROMPT_TEMPLATE = """请分析以下财经新闻：

标题：
{title}

正文：
{content}

按照指定JSON格式返回结果。"""


class EventService:
    def __init__(self, news_db=None, stocks_db=None):
        from config import Config
        self.llm = LLMClient()
        self.news_db = news_db or Config.NEWS_DB
        self.stocks_db = stocks_db or Config.STOCKS_DB
        self._init_table()

    def _init_table(self):
        with sqlite3.connect(self.news_db) as conn:
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
        return int(base * 0.7 + novelty * 0.3)

    def extract(self, title: str, content: str) -> dict:
        if not self.llm.available:
            return self._fallback()
        user_prompt = USER_PROMPT_TEMPLATE.format(title=title, content=content[:1000])
        for attempt in range(3):
            try:
                raw = self.llm.chat(SYSTEM_PROMPT, user_prompt, temperature=0.1)
                parsed = self._parse_json(raw)
                if parsed:
                    validated = self._validate(parsed)
                    if validated.get("event_type") != "OTHER" or validated["novelty_score"] > 0:
                        validated["raw_response"] = raw
                        return validated
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
            "event_type": "OTHER", "event_subtype": "",
            "industry": "", "sub_industry": "",
            "sentiment": "neutral", "importance": "C",
            "novelty_score": 0, "event_score": 0,
            "entities": [], "amount": 0.0, "amount_unit": "",
            "keywords": [], "ai_summary": "", "reason": "",
            "raw_response": "",
        }

    def process_news_item(self, news_item: dict) -> dict:
        result = self.extract(news_item["title"], news_item.get("content", ""))
        event_id = None
        with sqlite3.connect(self.news_db) as conn:
            conn.execute("""
                INSERT INTO event_analysis
                    (source_type, source_id, event_type, event_subtype,
                     industry, sub_industry, sentiment, importance,
                     novelty_score, event_score, entities_json, amount, amount_unit,
                     keywords_json, ai_summary, reason, raw_response)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "news", news_item["id"],
                result["event_type"], result["event_subtype"],
                result["industry"], result["sub_industry"],
                result["sentiment"], result["importance"],
                result["novelty_score"], result["event_score"],
                json.dumps(result["entities"], ensure_ascii=False),
                result["amount"], result["amount_unit"],
                json.dumps(result["keywords"], ensure_ascii=False),
                result["ai_summary"], result["reason"],
                result.get("raw_response", ""),
            ))
            event_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.execute("""
                UPDATE news SET sentiment=?, category=?, impact=?, ai_analysis=?, updated_at=?
                WHERE id=?
            """, (
                result["sentiment"], result["event_type"],
                result["event_score"], result["ai_summary"],
                datetime.now().isoformat(), news_item["id"],
            ))
        # Phase 8: Theme Discovery — 从关键词中发现新概念
        if result.get("keywords"):
            try:
                td = ThemeDiscovery()
                td.discover(result["keywords"], result.get("industry", ""))
            except Exception:
                pass
        # Phase 10: Event Clustering — 相似事件归簇
        if event_id and news_item.get("title"):
            try:
                ec = EventClustering()
                ec.cluster_event(event_id, news_item["title"],
                                 news_item.get("content", ""))
            except Exception:
                pass
        result["_event_id"] = event_id
        return result

    def get_recent_events(self, hours=24, limit=50) -> list:
        since = (datetime.now().timestamp() - hours * 3600)
        with sqlite3.connect(self.news_db) as conn:
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

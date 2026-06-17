"""概念发现引擎 — 从事件中发现新概念并管理生命周期

PRD 第一章: 概念发酵信息传导链
  源头信号(T-N) → 主力埋伏(T-3~T-1) → 盘面启动(T日) → 媒体扩散(T+1~T+3)

本模块负责: 从 AI 事件抽取结果中识别概念关键词，纳入候选池，管理升级。
"""
import hashlib
import json
import sqlite3
from datetime import datetime, timedelta
from config import Config


class ConceptDiscovery:
    def __init__(self, concept_db=None):
        self.concept_db = concept_db or Config.CONCEPT_DB

    # ──────────────────────────────────────────────
    # 核心: 从已分析新闻中发现概念
    # ──────────────────────────────────────────────

    def discover_from_analyzed_news(self, news_ids: list) -> list:
        """从已分析的新闻中批量发现概念候选"""
        if not news_ids:
            return []
        discovered = []
        with sqlite3.connect(Config.NEWS_DB) as conn:
            conn.row_factory = sqlite3.Row
            placeholders = ",".join("?" for _ in news_ids)
            rows = conn.execute(f"""
                SELECT e.event_id, e.source_id as news_id, e.event_type,
                       e.event_subtype, e.industry, e.sub_industry,
                       e.importance, e.event_score, e.keywords_json,
                       e.ai_summary, n.title, n.created_at
                FROM event_analysis e
                JOIN news n ON e.source_id = n.id
                WHERE e.source_id IN ({placeholders})
            """, news_ids).fetchall()

        for row in rows:
            row = dict(row)
            concepts = self._extract_concepts_from_event(row)
            for cpt in concepts:
                cid = self._upsert_concept(cpt, row)
                discovered.append({"concept_id": cid, "concept_name": cpt})
                self._link_event(cid, row)
        return discovered

    def discover_from_event(self, event: dict) -> list:
        """从单个事件中发现概念"""
        concepts = self._extract_concepts_from_event(event)
        discovered = []
        for cpt_name in concepts:
            cid = self._upsert_concept(cpt_name, event)
            discovered.append({"concept_id": cid, "concept_name": cpt_name})
            if event.get("_event_id"):
                self._link_event(cid, event)
        return discovered

    # ──────────────────────────────────────────────
    # 概念提取逻辑
    # ──────────────────────────────────────────────

    def _extract_concepts_from_event(self, event: dict) -> list:
        """从事件数据中提取概念关键词"""
        concepts = set()

        # 1. AI 提取的 concept_keywords (最可靠)
        keywords_json = event.get("keywords_json", "[]")
        if isinstance(keywords_json, str):
            try:
                all_keywords = json.loads(keywords_json)
            except json.JSONDecodeError:
                all_keywords = []
        else:
            all_keywords = keywords_json if isinstance(keywords_json, list) else []

        # concept_keywords 字段 (V2新增)
        concept_kw = event.get("concept_keywords", [])
        if isinstance(concept_kw, str):
            try:
                concept_kw = json.loads(concept_kw)
            except json.JSONDecodeError:
                concept_kw = []
        if isinstance(concept_kw, list):
            for k in concept_kw:
                k = str(k).strip()
                if 2 <= len(k) <= 20:
                    concepts.add(k)

        # 2. 高重要性事件 → 行业/子行业作为概念
        importance = event.get("importance", "C")
        industry = event.get("industry", "").strip()
        sub_industry = event.get("sub_industry", "").strip()
        if importance in ("S", "A"):
            if industry and len(industry) >= 2:
                concepts.add(industry)
            if sub_industry and len(sub_industry) >= 2:
                concepts.add(sub_industry)

        # 3. 从普通 keywords 中筛选可能的概念词
        #    过滤掉太泛的词 (如 "增长", "利润")
        GENERIC_WORDS = {
            "增长", "利润", "营收", "市场", "投资", "合作", "发展", "创新",
            "技术", "产品", "业务", "项目", "合同", "订单", "公告", "报告",
            "股票", "公司", "行业", "板块", "概念", "题材", "政策", "利好",
        }
        for kw in all_keywords:
            kw = str(kw).strip()
            if 2 <= len(kw) <= 15 and kw not in GENERIC_WORDS:
                # 只有看起来像行业/技术/题材名词的才纳入
                if self._looks_like_concept(kw):
                    concepts.add(kw)

        return list(concepts)

    def _looks_like_concept(self, keyword: str) -> bool:
        """判断一个关键词是否像"概念/题材"名"""
        # 包含这些字的词大概率是概念名
        concept_indicators = [
            "经济", "电池", "芯片", "半导体", "机器人", "智能", "数据",
            "能源", "汽车", "医药", "生物", "航空", "航天", "量子",
            "元宇宙", "区块链", "算力", "光模块", "储能", "光伏",
            "氢能", "核能", "风电", "新材料", "碳纤维", "石墨烯",
            "基因", "细胞", "创新药", "中药", "消费", "白酒",
            "地产", "金融", "银行", "券商", "保险",
            "军工", "船舶", "卫星", "导航", "通信", "5G", "6G",
            "低空", "飞行", "无人驾驶", "自动驾驶", "车路协同",
            "AI", "大模型", "AIGC", "算力", "液冷", "服务器",
            "教育", "传媒", "游戏", "短剧",
        ]
        for indicator in concept_indicators:
            if indicator in keyword or keyword in indicator:
                return True
        # 长度 3-8 且全中文的词较可能是概念名
        if 3 <= len(keyword) <= 8 and all('\u4e00' <= c <= '\u9fff' for c in keyword):
            return True
        return False

    # ──────────────────────────────────────────────
    # 概念入库 + 升级
    # ──────────────────────────────────────────────

    def _upsert_concept(self, concept_name: str, event: dict) -> str:
        """新增或更新概念候选，返回 concept_id"""
        concept_id = self._make_concept_id(concept_name)
        now = datetime.now().isoformat()
        today = datetime.now().strftime("%Y-%m-%d")
        event_id = str(event.get("_event_id", event.get("event_id", "")))

        with sqlite3.connect(self.concept_db) as conn:
            existing = conn.execute(
                "SELECT mention_count, mention_days, source_events, first_seen FROM concept_candidate WHERE concept_id=?",
                (concept_id,)
            ).fetchone()

            if existing:
                old_count, old_days, old_events, first_seen = existing
                # 计算 mention_days: 检查是否新的一天
                try:
                    first_dt = datetime.fromisoformat(first_seen)
                    days_diff = (datetime.now() - first_dt).days + 1
                    new_days = max(old_days, min(days_diff, 999))
                except Exception:
                    new_days = old_days + 1

                new_count = old_count + 1
                events_list = old_events.split(",") if old_events else []
                if event_id and event_id not in events_list:
                    events_list.append(event_id)

                conn.execute("""
                    UPDATE concept_candidate SET
                        mention_count=?, mention_days=?, last_seen=?,
                        source_events=?, updated_at=?
                    WHERE concept_id=?
                """, (new_count, new_days, now,
                      ",".join(events_list[-20:]), now, concept_id))
            else:
                industry = event.get("industry", "")
                keywords = event.get("keywords_json", "[]")
                if isinstance(keywords, list):
                    keywords = ",".join(str(k) for k in keywords[:10])

                conn.execute("""
                    INSERT INTO concept_candidate
                        (concept_id, concept_name, concept_type, status,
                         first_seen, last_seen, mention_count, mention_days,
                         source_events, keywords, industry, lifecycle)
                    VALUES (?, ?, ?, 'candidate', ?, ?, 1, 1, ?, ?, ?, 'BIRTH')
                """, (concept_id, concept_name,
                      self._infer_type(event.get("event_type", "")),
                      now, now, event_id, keywords, industry))
            conn.commit()
        return concept_id

    def _link_event(self, concept_id: str, event: dict):
        """关联概念与事件"""
        event_id = event.get("_event_id", event.get("event_id"))
        if not event_id:
            return
        news_id = event.get("news_id", event.get("source_id", ""))
        try:
            with sqlite3.connect(self.concept_db) as conn:
                conn.execute("""
                    INSERT OR IGNORE INTO concept_event
                        (concept_id, event_id, news_id, event_type,
                         event_score, news_title)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (concept_id, event_id, news_id,
                      event.get("event_type", ""),
                      event.get("event_score", 0),
                      event.get("title", event.get("ai_summary", ""))[:100]))
                conn.commit()
        except Exception:
            pass

    def check_upgrades(self) -> list:
        """检查并执行概念状态升级
        - candidate → observing: mention_count >= 3 且 mention_days >= 2
        - observing → validated: mention_count >= 5 且 有事件支撑
        """
        upgrades = []
        with sqlite3.connect(self.concept_db) as conn:
            conn.row_factory = sqlite3.Row

            # candidate → observing
            candidates = conn.execute("""
                SELECT concept_id, concept_name, mention_count, mention_days
                FROM concept_candidate
                WHERE status='candidate' AND mention_count >= 3 AND mention_days >= 2
            """).fetchall()
            for row in candidates:
                conn.execute("""
                    UPDATE concept_candidate
                    SET status='observing', lifecycle='GROWING', updated_at=?
                    WHERE concept_id=?
                """, (datetime.now().isoformat(), row["concept_id"]))
                upgrades.append(dict(row, status="observing"))

            # observing → validated (触发7信号验证)
            observers = conn.execute("""
                SELECT concept_id, concept_name, mention_count, mention_days
                FROM concept_candidate
                WHERE status='observing' AND mention_count >= 5
            """).fetchall()
            for row in observers:
                conn.execute("""
                    UPDATE concept_candidate
                    SET status='validated', lifecycle='PEAK', updated_at=?
                    WHERE concept_id=?
                """, (datetime.now().isoformat(), row["concept_id"]))
                upgrades.append(dict(row, status="validated"))

            # 衰减: 超过 72h 无新增提及 → DECLINING
            cutoff = (datetime.now() - timedelta(hours=72)).isoformat()
            conn.execute("""
                UPDATE concept_candidate
                SET lifecycle='DECLINING'
                WHERE last_seen < ? AND lifecycle NOT IN ('DEAD', 'DECLINING')
                AND status != 'validated'
            """, (cutoff,))

            # 超过 7 天无新增 → DEAD
            dead_cutoff = (datetime.now() - timedelta(days=7)).isoformat()
            conn.execute("""
                UPDATE concept_candidate
                SET lifecycle='DEAD'
                WHERE last_seen < ? AND lifecycle = 'DECLINING'
            """, (dead_cutoff,))

            conn.commit()
        return upgrades

    # ──────────────────────────────────────────────
    # 辅助方法
    # ──────────────────────────────────────────────

    def _make_concept_id(self, name: str) -> str:
        """生成概念ID: CPT_ + 名称hash前8位"""
        h = hashlib.md5(name.encode()).hexdigest()[:8]
        return f"CPT_{h}"

    def _infer_type(self, event_type: str) -> str:
        """从事件类型推断概念类型"""
        mapping = {
            "POLICY": "policy",
            "TECHNOLOGY": "tech",
            "ORDER": "business",
            "EARNINGS": "earnings",
            "MNA": "capital",
            "CAPITAL": "capital",
            "RISK": "risk",
        }
        return mapping.get(event_type, "general")

    def get_concepts(self, status=None, limit=100) -> list:
        """查询概念候选池"""
        with sqlite3.connect(self.concept_db) as conn:
            conn.row_factory = sqlite3.Row
            if status:
                rows = conn.execute("""
                    SELECT * FROM concept_candidate
                    WHERE status=? ORDER BY mention_count DESC LIMIT ?
                """, (status, limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM concept_candidate
                    WHERE lifecycle != 'DEAD'
                    ORDER BY mention_count DESC LIMIT ?
                """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    def get_concept_events(self, concept_id: str) -> list:
        """获取概念关联的事件列表"""
        with sqlite3.connect(self.concept_db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM concept_event
                WHERE concept_id=? ORDER BY created_at DESC
            """, (concept_id,)).fetchall()
            return [dict(r) for r in rows]

    def get_concept_stocks(self, concept_id: str) -> list:
        """获取概念关联的股票"""
        with sqlite3.connect(self.concept_db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM concept_stock
                WHERE concept_id=? ORDER BY is_core DESC, role ASC
            """, (concept_id,)).fetchall()
            return [dict(r) for r in rows]

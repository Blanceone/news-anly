"""股票关联服务 — Phase 3

事件 → 股票映射：
1. theme_stock_mapping 表：主题 → 受益股票（人工维护的知识库）
2. event_stock_mapping 表：事件 → 关联股票（AI自动匹配）
3. 事件发布时通过关键词匹配主题，找出受益股票
"""
import json
import sqlite3
from datetime import datetime

INITIAL_THEMES = {
    "AI": {
        "name": "人工智能",
        "keywords": ["AI", "人工智能", "大模型", "GPT", "多模态", "神经网络"],
        "stocks": [
            ("002230", "科大讯飞", 1, "AI语音龙头"),
            ("002415", "海康威视", 1, "AI视觉龙头"),
            ("688256", "寒武纪", 1, "AI芯片"),
            ("300496", "中科创达", 2, "AI操作系统"),
            ("688088", "虹软科技", 2, "AI视觉算法"),
            ("300624", "万兴科技", 3, "AI应用"),
        ],
    },
    "算力": {
        "name": "算力基础设施",
        "keywords": ["算力", "光模块", "服务器", "数据中心", "CPO", "HBM"],
        "stocks": [
            ("300308", "中际旭创", 1, "光模块龙头"),
            ("300502", "新易盛", 1, "光模块"),
            ("300394", "天孚通信", 2, "光器件"),
            ("601138", "工业富联", 1, "AI服务器"),
            ("603019", "中科曙光", 1, "算力服务器"),
            ("000977", "浪潮信息", 1, "AI服务器"),
            ("688041", "海光信息", 1, "CPU/算力芯片"),
        ],
    },
    "半导体": {
        "name": "半导体",
        "keywords": ["半导体", "芯片", "晶圆", "封测", "EDA", "光刻"],
        "stocks": [
            ("688981", "中芯国际", 1, "晶圆代工龙头"),
            ("002371", "北方华创", 1, "半导体设备"),
            ("603501", "韦尔股份", 1, "芯片设计"),
            ("600584", "长电科技", 1, "封测龙头"),
            ("301269", "华大九天", 2, "EDA软件"),
            ("688012", "中微公司", 1, "刻蚀设备"),
            ("688072", "拓荆科技", 2, "薄膜沉积设备"),
        ],
    },
    "机器人": {
        "name": "机器人",
        "keywords": ["机器人", "人形机器人", "减速器", "伺服", "具身智能"],
        "stocks": [
            ("002031", "巨轮智能", 1, "RV减速器"),
            ("688017", "绿的谐波", 1, "谐波减速器"),
            ("002747", "埃斯顿", 1, "工业机器人"),
            ("300124", "汇川技术", 1, "伺服系统"),
            ("601689", "拓普集团", 2, "机器人执行器"),
            ("688160", "步科股份", 2, "机器人控制"),
        ],
    },
    "创新药": {
        "name": "创新药",
        "keywords": ["创新药", "生物药", "CXO", "临床试验", "FDA"],
        "stocks": [
            ("600276", "恒瑞医药", 1, "创新药龙头"),
            ("688235", "百济神州", 1, "创新药"),
            ("603259", "药明康德", 1, "CXO龙头"),
            ("300759", "康龙化成", 1, "CXO"),
            ("002821", "凯莱英", 2, "CDMO"),
        ],
    },
}


class StockService:
    def __init__(self, db_path="news.db"):
        self.db_path = db_path
        self._init_table()
        self._seed_themes()

    def _init_table(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS stock_basic (
                    stock_code TEXT PRIMARY KEY,
                    stock_name TEXT NOT NULL,
                    industry TEXT,
                    market_value REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS theme_stock_mapping (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    theme_key TEXT NOT NULL,
                    theme_name TEXT NOT NULL,
                    stock_code TEXT NOT NULL,
                    stock_name TEXT NOT NULL,
                    benefit_level INTEGER,
                    benefit_reason TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS event_stock_mapping (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER NOT NULL,
                    stock_code TEXT NOT NULL,
                    stock_name TEXT NOT NULL,
                    benefit_level INTEGER,
                    benefit_score INTEGER,
                    match_reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def _seed_themes(self):
        with sqlite3.connect(self.db_path) as conn:
            for theme_key, theme_data in INITIAL_THEMES.items():
                existing = conn.execute(
                    "SELECT COUNT(*) FROM theme_stock_mapping WHERE theme_key=?", (theme_key,)
                ).fetchone()[0]
                if existing > 0:
                    continue
                for code, name, level, reason in theme_data["stocks"]:
                    conn.execute("""
                        INSERT OR IGNORE INTO stock_basic (stock_code, stock_name)
                        VALUES (?, ?)
                    """, (code, name))
                    conn.execute("""
                        INSERT INTO theme_stock_mapping
                            (theme_key, theme_name, stock_code, stock_name, benefit_level, benefit_reason)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (theme_key, theme_data["name"], code, name, level, reason))
            conn.commit()
        print(f"  [股票] 已初始化 {sum(len(t['stocks']) for t in INITIAL_THEMES.values())} 条主题映射")

    def match_event_to_stocks(self, event: dict) -> list:
        """根据事件的关键词/行业匹配主题和股票"""
        matched = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            keywords = [k.lower() for k in event.get("keywords", [])]
            industry = (event.get("industry") or "").lower()
            sub_industry = (event.get("sub_industry") or "").lower()
            all_text = f"{industry} {sub_industry} {' '.join(keywords)}"

            for theme_key, theme_data in INITIAL_THEMES.items():
                theme_kws = [kw.lower() for kw in theme_data["keywords"]]
                if any(kw in all_text for kw in theme_kws):
                    rows = conn.execute("""
                        SELECT stock_code, stock_name, benefit_level, benefit_reason
                        FROM theme_stock_mapping
                        WHERE theme_key=?
                        ORDER BY benefit_level ASC
                    """, (theme_key,)).fetchall()
                    for r in rows:
                        matched.append(dict(r))
        return matched

    def process_event_stocks(self, event_id: int, event: dict):
        """为事件创建股票关联"""
        matched = self.match_event_to_stocks(event)
        if not matched:
            return
        benefit_scores = {1: 95, 2: 80, 3: 60}
        with sqlite3.connect(self.db_path) as conn:
            for stock in matched:
                level = stock["benefit_level"]
                score = benefit_scores.get(level, 40)
                conn.execute("""
                    INSERT INTO event_stock_mapping
                        (event_id, stock_code, stock_name, benefit_level, benefit_score, match_reason)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (event_id, stock["stock_code"], stock["stock_name"],
                      level, score, stock["benefit_reason"]))
            conn.commit()

    def get_top_stocks(self, hours=24, limit=20) -> list:
        """获取TOP N 受益股评分"""
        since = (datetime.now().timestamp() - hours * 3600)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT
                    es.stock_code,
                    es.stock_name,
                    AVG(es.benefit_score) as avg_benefit,
                    AVG(e.event_score) as avg_event,
                    COUNT(DISTINCT e.event_id) as event_count,
                    GROUP_CONCAT(DISTINCT e.event_type) as event_types
                FROM event_stock_mapping es
                JOIN event_analysis e ON es.event_id = e.event_id
                WHERE e.created_at > datetime(?, 'unixepoch')
                GROUP BY es.stock_code, es.stock_name
                ORDER BY avg_benefit DESC, avg_event DESC
                LIMIT ?
            """, (since, limit)).fetchall()
            return [dict(r) for r in rows]

    def get_stock_events(self, stock_code: str, hours=72) -> list:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT e.event_type, e.industry, e.sentiment, e.importance,
                       e.event_score, e.ai_summary, e.created_at,
                       es.benefit_level, es.benefit_score, es.match_reason
                FROM event_stock_mapping es
                JOIN event_analysis e ON es.event_id = e.event_id
                WHERE es.stock_code=? AND e.created_at > datetime(?, 'unixepoch')
                ORDER BY e.event_score DESC
            """, (stock_code, (datetime.now().timestamp() - hours * 3600))).fetchall()
            return [dict(r) for r in rows]

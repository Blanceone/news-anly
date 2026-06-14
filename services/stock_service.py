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
    "先进封装": {
        "name": "先进封装",
        "keywords": ["先进封装", "Chiplet", "HBM", "SiP", "3D封装", "封装"],
        "stocks": [
            ("600584", "长电科技", 1, "封装龙头"),
            ("002156", "通富微电", 1, "AMD封装链"),
            ("002185", "华天科技", 2, "先进封装"),
            ("603005", "晶方科技", 1, "晶圆级封装"),
            ("688072", "拓荆科技", 2, "薄膜沉积/先进封装设备"),
        ],
    },
    "具身智能": {
        "name": "具身智能",
        "keywords": ["具身智能", "人形机器人", "灵巧手", "传感器", "执行器"],
        "stocks": [
            ("601689", "拓普集团", 1, "机器人执行器"),
            ("002050", "三花智控", 1, "机器人关节"),
            ("603728", "鸣志电器", 1, "空心杯电机/灵巧手"),
            ("688017", "绿的谐波", 1, "谐波减速器"),
            ("300124", "汇川技术", 2, "伺服驱动"),
            ("688160", "步科股份", 2, "机器人控制系统"),
        ],
    },
    "低空经济": {
        "name": "低空经济",
        "keywords": ["低空经济", "无人机", "eVTOL", "空管", "飞行汽车"],
        "stocks": [
            ("002097", "山河智能", 1, "无人机"),
            ("300696", "爱乐达", 1, "空管系统"),
            ("600038", "中直股份", 1, "直升机/eVTOL"),
            ("002023", "海特高新", 2, "飞行模拟/维修"),
            ("300424", "航新科技", 2, "航空保障"),
        ],
    },
    "新能源": {
        "name": "新能源",
        "keywords": ["新能源", "锂电池", "光伏", "储能", "风电", "新能源汽车"],
        "stocks": [
            ("300750", "宁德时代", 1, "锂电池龙头"),
            ("601012", "隆基绿能", 1, "光伏龙头"),
            ("002459", "晶澳科技", 1, "光伏组件"),
            ("300274", "阳光电源", 1, "逆变器/储能"),
            ("002129", "中环股份", 2, "光伏硅片"),
        ],
    },
    "CPO": {
        "name": "CPO/光通信",
        "keywords": ["CPO", "光通信", "光模块", "硅光", "1.6T"],
        "stocks": [
            ("300308", "中际旭创", 1, "光模块龙头/CPO"),
            ("300502", "新易盛", 1, "光模块/硅光"),
            ("300394", "天孚通信", 1, "光器件/CPO"),
            ("688205", "德科立", 2, "光模块/CPO"),
            ("301165", "锐捷网络", 2, "光通信设备"),
        ],
    },
}


class StockService:
    def __init__(self, db_path=None):
        from config import Config
        self.db_path = db_path or Config.STOCKS_DB
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
                    benefit_type TEXT DEFAULT 'DIRECT',
                    benefit_path TEXT,
                    match_reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            for col in ("benefit_type", "benefit_path"):
                try:
                    conn.execute(f"ALTER TABLE event_stock_mapping ADD COLUMN {col} TEXT")
                except sqlite3.OperationalError:
                    pass
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
        """根据事件的关键词/行业匹配主题和股票 — 关键词+Embedding双匹配"""
        matched = set()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            keywords = [k.lower() for k in event.get("keywords", [])]
            industry = (event.get("industry") or "").lower()
            sub_industry = (event.get("sub_industry") or "").lower()
            all_text = f"{industry} {sub_industry} {' '.join(keywords)}"

            # 1. 关键词匹配
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
                        matched.add((r["stock_code"], r["stock_name"],
                                     r["benefit_level"], r["benefit_reason"], "keyword"))

            # 2. Embedding 语义匹配 (Phase 9)
            try:
                from services.embedding_service import EmbeddingService
                em = EmbeddingService()
                emb_matches = em.match_event(event.get("keywords", []),
                                              event.get("industry", ""),
                                              event.get("sub_industry", ""))
                for m in emb_matches:
                    tname = m["theme_name"]
                    for theme_key, theme_data in INITIAL_THEMES.items():
                        if theme_data["name"] == tname:
                            rows = conn.execute("""
                                SELECT stock_code, stock_name, benefit_level, benefit_reason
                                FROM theme_stock_mapping
                                WHERE theme_key=?
                                ORDER BY benefit_level ASC
                            """, (theme_key,)).fetchall()
                            for r in rows:
                                matched.add((r["stock_code"], r["stock_name"],
                                             r["benefit_level"], r["benefit_reason"], "embedding"))
                            break
            except Exception:
                pass

        return [{"stock_code": c, "stock_name": n, "benefit_level": l, "benefit_reason": r, "_match_by": m}
                for c, n, l, r, m in matched]

    def _assign_benefit_type(self, stock: dict, match_source: str) -> str:
        """根据匹配来源和受益层级分配 benefit_type"""
        level = stock.get("benefit_level", 3)
        if match_source == "keyword":
            return "DIRECT" if level == 1 else "INDIRECT"
        if match_source == "embedding":
            return "INDIRECT"
        return "SENTIMENT"

    def _build_benefit_path(self, stock: dict, match_source: str) -> str:
        level = stock.get("benefit_level", 3)
        if match_source == "keyword":
            return f"关键词匹配(level={level})"
        if match_source == "embedding":
            return f"语义匹配(level={level})"
        return "其他"

    def process_event_stocks(self, event_id: int, event: dict):
        """为事件创建股票关联 — 含受益链分层"""
        matched = self.match_event_to_stocks(event)
        if not matched:
            return
        benefit_scores = {1: 95, 2: 80, 3: 60}
        with sqlite3.connect(self.db_path) as conn:
            for stock in matched:
                level = stock["benefit_level"]
                score = benefit_scores.get(level, 40)
                # 判断 matching source
                reason = stock.get("benefit_reason", "")
                src = "embedding" if stock.get("_match_by") == "embedding" else "keyword"
                btype = self._assign_benefit_type(stock, src)
                bpath = self._build_benefit_path(stock, src)
                conn.execute("""
                    INSERT INTO event_stock_mapping
                        (event_id, stock_code, stock_name, benefit_level, benefit_score,
                         benefit_type, benefit_path, match_reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (event_id, stock["stock_code"], stock["stock_name"],
                      level, score, btype, bpath, reason))
            conn.commit()

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

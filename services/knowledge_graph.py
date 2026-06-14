"""知识图谱 — Phase 4

图谱结构：Theme → Industry → Technology → Product → Stock
推理能力：事件关键词 → 匹配实体 → BFS遍历 → 受益股票排序

V1 覆盖：AI/算力/半导体/先进封装/光模块/机器人/低空经济/创新药/新能源
"""
import json
import sqlite3
from collections import defaultdict


SEED = {
    "entities": [
        # ── Themes ──
        ("theme", "人工智能", "AI、大模型、深度学习"),
        ("theme", "算力基础设施", "算力、数据中心、服务器"),
        ("theme", "半导体", "芯片、集成电路、晶圆"),
        ("theme", "机器人", "工业机器人、人形机器人、减速器"),
        ("theme", "创新药", "生物药、CXO、临床试验"),
        ("theme", "低空经济", "无人机、eVTOL、空管"),
        ("theme", "新能源", "光伏、锂电、储能"),
        ("theme", "先进封装", "Chiplet、HBM、SiP"),
        # ── Industries ──
        ("industry", "AI芯片", "GPU、NPU、AI加速"),
        ("industry", "光模块", "光通信、CPO、硅光"),
        ("industry", "服务器", "AI服务器、通用服务器"),
        ("industry", "晶圆代工", "晶圆制造、Foundry"),
        ("industry", "半导体设备", "刻蚀、薄膜沉积、光刻"),
        ("industry", "封测", "封装测试、先进封装"),
        ("industry", "减速器", "RV减速器、谐波减速器"),
        ("industry", "CXO", "药物研发外包、CDMO"),
        # ── Technologies ──
        ("technology", "Chiplet", "芯粒、先进封装、互联"),
        ("technology", "HBM", "高带宽内存、3D堆叠"),
        ("technology", "CPO", "共封装光学、硅光集成"),
        ("technology", "800G光模块", "高速光模块、数通"),
        ("technology", "AI服务器", "GPU服务器、训推一体"),
        ("technology", "EDA", "电子设计自动化"),
        ("technology", "先进制程", "7nm、5nm、3nm"),
        # ── Products ──
        ("product", "GPU芯片", "图形处理器、AI加速卡"),
        ("product", "AI服务器产品", "训练服务器、推理服务器"),
        ("product", "光模块产品", "400G、800G、1.6T光模块"),
        ("product", "减速器产品", "RV减速器、谐波减速器"),
        ("product", "封装服务", "先进封装、SiP封装"),
        # ── New themes ──
        ("theme", "具身智能", "人形机器人、灵巧手、传感器、执行器"),
        ("theme", "CPO/光通信", "CPO、共封装光学、硅光、光模块"),
        # ── New industries ──
        ("industry", "机器人关节", "执行器、灵巧手、空心杯电机"),
        ("industry", "光伏", "光伏组件、逆变器、硅片"),
        ("industry", "锂电池", "动力电池、储能电池、正负极"),
        # ── New technologies ──
        ("technology", "机器人灵巧手", "空心杯电机、精密传动"),
        ("technology", "储能", "电池储能、液冷、PCS、逆变器"),
        # ── New products ──
        ("product", "机器人灵巧手产品", "灵巧手、末端执行器"),
        ("product", "储能产品", "储能系统、逆变器"),
        # ── Company entities (Phase 11) ──
        ("company", "华为", "通信设备、芯片设计、云计算"),
        ("company", "英伟达", "GPU、AI芯片、自动驾驶"),
        ("company", "苹果", "消费电子、手机、芯片设计"),
        ("company", "特斯拉", "电动车、机器人、储能"),
        ("company", "比亚迪", "电动车、锂电池、半导体"),
        ("company", "三星", "半导体、存储、消费电子"),
        ("company", "台积电", "晶圆代工、先进制程"),
        ("company", "高通", "通信芯片、手机SoC"),
        ("company", "AMD", "CPU、GPU、芯片设计"),
        ("company", "英特尔", "CPU、芯片制造、AI芯片"),
    ],
    "relations": [
        # Theme → Industry
        ("theme", "人工智能", "industry", "AI芯片", "CONTAINS", 90),
        ("theme", "算力基础设施", "industry", "光模块", "CONTAINS", 95),
        ("theme", "算力基础设施", "industry", "服务器", "CONTAINS", 95),
        ("theme", "半导体", "industry", "晶圆代工", "CONTAINS", 95),
        ("theme", "半导体", "industry", "半导体设备", "CONTAINS", 90),
        ("theme", "半导体", "industry", "封测", "CONTAINS", 85),
        ("theme", "机器人", "industry", "减速器", "CONTAINS", 95),
        ("theme", "创新药", "industry", "CXO", "CONTAINS", 90),
        ("theme", "先进封装", "industry", "封测", "CONTAINS", 95),
        ("theme", "先进封装", "industry", "半导体设备", "CONTAINS", 80),
        # Industry → Technology
        ("industry", "AI芯片", "technology", "Chiplet", "CONTAINS", 85),
        ("industry", "AI芯片", "technology", "HBM", "CONTAINS", 80),
        ("industry", "光模块", "technology", "CPO", "CONTAINS", 90),
        ("industry", "光模块", "technology", "800G光模块", "CONTAINS", 95),
        ("industry", "服务器", "technology", "AI服务器", "CONTAINS", 95),
        ("industry", "晶圆代工", "technology", "先进制程", "CONTAINS", 95),
        ("industry", "半导体设备", "technology", "先进制程", "CONTAINS", 85),
        ("industry", "封测", "technology", "Chiplet", "CONTAINS", 90),
        ("industry", "封测", "technology", "HBM", "CONTAINS", 80),
        ("industry", "减速器", "technology", "Chiplet", "CONTAINS", 0),
        # New theme → industry
        ("theme", "具身智能", "industry", "机器人关节", "CONTAINS", 95),
        ("theme", "具身智能", "industry", "减速器", "CONTAINS", 85),
        ("theme", "CPO/光通信", "industry", "光模块", "CONTAINS", 95),
        ("theme", "新能源", "industry", "光伏", "CONTAINS", 90),
        ("theme", "新能源", "industry", "锂电池", "CONTAINS", 95),
        # New industry → technology
        ("industry", "机器人关节", "technology", "机器人灵巧手", "CONTAINS", 95),
        ("industry", "光伏", "technology", "储能", "CONTAINS", 85),
        ("industry", "锂电池", "technology", "储能", "CONTAINS", 90),
        # Technology → Product
        ("technology", "Chiplet", "product", "封装服务", "ENABLE", 95),
        ("technology", "HBM", "product", "GPU芯片", "ENABLE", 90),
        ("technology", "AI服务器", "product", "AI服务器产品", "ENABLE", 95),
        ("technology", "800G光模块", "product", "光模块产品", "ENABLE", 95),
        ("technology", "CPO", "product", "光模块产品", "ENABLE", 80),
        ("technology", "先进制程", "product", "GPU芯片", "ENABLE", 90),
        ("technology", "EDA", "product", "GPU芯片", "ENABLE", 70),
        # ── Company → Industry / Technology / Product (Phase 11) ──
        ("company", "华为", "industry", "AI芯片", "USES", 90),
        ("company", "华为", "industry", "封测", "USES", 85),
        ("company", "华为", "technology", "先进制程", "USES", 90),
        ("company", "华为", "technology", "Chiplet", "USES", 85),
        ("company", "英伟达", "industry", "AI芯片", "CONTAINS", 95),
        ("company", "特斯拉", "industry", "机器人关节", "USES", 85),
        ("company", "特斯拉", "technology", "储能", "USES", 80),
        ("company", "比亚迪", "industry", "锂电池", "CONTAINS", 90),
        ("company", "比亚迪", "technology", "储能", "USES", 85),
        ("company", "台积电", "industry", "晶圆代工", "CONTAINS", 95),
        ("company", "台积电", "technology", "先进制程", "CONTAINS", 95),
        # ── Company → Stock (SUPPLIER / CUSTOMER) ──
        ("company", "华为", "stock", "002156", "SUPPLIER", 90),
        ("company", "华为", "stock", "600584", "SUPPLIER", 85),
        ("company", "华为", "stock", "002185", "SUPPLIER", 80),
        ("company", "华为", "stock", "603005", "SUPPLIER", 80),
        ("company", "英伟达", "stock", "688041", "SUPPLIER", 90),
        ("company", "英伟达", "stock", "688256", "SUPPLIER", 85),
        ("company", "特斯拉", "stock", "601689", "SUPPLIER", 85),
        ("company", "特斯拉", "stock", "002050", "SUPPLIER", 80),
        ("company", "特斯拉", "stock", "300750", "SUPPLIER", 75),
        ("company", "苹果", "stock", "002415", "SUPPLIER", 85),
        ("company", "苹果", "stock", "600584", "SUPPLIER", 80),
        ("company", "比亚迪", "stock", "300750", "CUSTOMER", 80),
        ("company", "比亚迪", "stock", "002129", "SUPPLIER", 75),
        # ── Company ↔ Company (COMPETITOR) ──
        ("company", "华为", "company", "高通", "COMPETITOR", 80),
        ("company", "英伟达", "company", "AMD", "COMPETITOR", 85),
        ("company", "英伟达", "company", "英特尔", "COMPETITOR", 80),
        ("company", "台积电", "company", "三星", "COMPETITOR", 85),
        ("company", "比亚迪", "company", "特斯拉", "COMPETITOR", 75),
        # Product → Stock
        ("product", "GPU芯片", "stock", "688041", "BENEFIT", 95),
        ("product", "GPU芯片", "stock", "688256", "BENEFIT", 90),
        ("product", "AI服务器产品", "stock", "601138", "BENEFIT", 95),
        ("product", "AI服务器产品", "stock", "000977", "BENEFIT", 90),
        ("product", "AI服务器产品", "stock", "603019", "BENEFIT", 90),
        ("product", "光模块产品", "stock", "300308", "BENEFIT", 95),
        ("product", "光模块产品", "stock", "300502", "BENEFIT", 92),
        ("product", "光模块产品", "stock", "300394", "BENEFIT", 80),
        ("product", "封装服务", "stock", "600584", "BENEFIT", 95),
        ("product", "封装服务", "stock", "002156", "BENEFIT", 92),
        ("product", "封装服务", "stock", "002185", "BENEFIT", 70),
        ("product", "减速器产品", "stock", "002031", "BENEFIT", 95),
        ("product", "减速器产品", "stock", "688017", "BENEFIT", 90),
        ("product", "封装服务", "stock", "603005", "BENEFIT", 85),
        ("product", "机器人灵巧手产品", "stock", "603728", "BENEFIT", 95),
        ("product", "机器人灵巧手产品", "stock", "002050", "BENEFIT", 90),
        ("product", "储能产品", "stock", "300274", "BENEFIT", 95),
        ("product", "储能产品", "stock", "300750", "BENEFIT", 85),
    ],
    "direct_benefit": [
        ("theme", "人工智能", "stock", "002230", 95, "AI语音龙头"),
        ("theme", "人工智能", "stock", "002415", 90, "AI视觉龙头"),
        ("theme", "人工智能", "stock", "300496", 80, "AI操作系统"),
        ("theme", "人工智能", "stock", "688088", 75, "AI视觉算法"),
        ("theme", "算力基础设施", "stock", "601138", 95, "AI服务器龙头"),
        ("theme", "算力基础设施", "stock", "300308", 95, "光模块龙头"),
        ("theme", "算力基础设施", "stock", "000977", 90, "AI服务器"),
        ("theme", "算力基础设施", "stock", "300502", 90, "光模块"),
        ("theme", "算力基础设施", "stock", "603019", 85, "算力服务器"),
        ("theme", "算力基础设施", "stock", "688041", 90, "算力芯片"),
        ("theme", "半导体", "stock", "688981", 95, "晶圆代工龙头"),
        ("theme", "半导体", "stock", "002371", 95, "半导体设备"),
        ("theme", "半导体", "stock", "600584", 90, "封测龙头"),
        ("theme", "半导体", "stock", "603501", 90, "芯片设计"),
        ("theme", "半导体", "stock", "688012", 90, "刻蚀设备"),
        ("theme", "半导体", "stock", "301269", 75, "EDA软件"),
        ("theme", "机器人", "stock", "002031", 95, "RV减速器"),
        ("theme", "机器人", "stock", "688017", 95, "谐波减速器"),
        ("theme", "机器人", "stock", "002747", 85, "工业机器人"),
        ("theme", "机器人", "stock", "300124", 85, "伺服系统"),
        ("theme", "创新药", "stock", "600276", 95, "创新药龙头"),
        ("theme", "创新药", "stock", "688235", 90, "创新药"),
        ("theme", "创新药", "stock", "603259", 90, "CXO龙头"),
        ("theme", "创新药", "stock", "300759", 85, "CXO"),
        ("theme", "新能源", "stock", "300750", 95, "锂电池龙头"),
        ("theme", "新能源", "stock", "601012", 90, "光伏龙头"),
        ("theme", "新能源", "stock", "002459", 85, "光伏"),
        ("theme", "新能源", "stock", "300274", 85, "储能逆变器"),
        ("theme", "低空经济", "stock", "002097", 85, "无人机"),
        ("theme", "低空经济", "stock", "300696", 80, "空管系统"),
        ("theme", "低空经济", "stock", "600038", 85, "直升机/eVTOL"),
        ("theme", "先进封装", "stock", "600584", 95, "封装龙头"),
        ("theme", "先进封装", "stock", "002156", 92, "AMD封装链"),
        ("theme", "先进封装", "stock", "002185", 75, "先进封装"),
        ("theme", "先进封装", "stock", "603005", 90, "晶圆级封装"),
        ("theme", "具身智能", "stock", "603728", 95, "空心杯电机/灵巧手"),
        ("theme", "具身智能", "stock", "002050", 90, "机器人关节"),
        ("theme", "具身智能", "stock", "601689", 90, "机器人执行器"),
        ("theme", "具身智能", "stock", "688017", 85, "谐波减速器"),
        ("theme", "CPO/光通信", "stock", "300308", 95, "光模块龙头"),
        ("theme", "CPO/光通信", "stock", "300502", 92, "光模块/硅光"),
        ("theme", "CPO/光通信", "stock", "300394", 85, "光器件/CPO"),
    ],
}


class KnowledgeGraph:
    def __init__(self, db_path=None):
        from config import Config
        self.db_path = db_path or Config.STOCKS_DB
        self._init_table()
        self._seed()

    def _init_table(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS kg_entity (
                    entity_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    UNIQUE(entity_type, name)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS kg_relation (
                    relation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_type TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_name TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    weight REAL DEFAULT 0,
                    UNIQUE(source_type, source_name, target_type, target_name, relation_type)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS kg_direct_benefit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_type TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    stock_code TEXT NOT NULL,
                    weight REAL NOT NULL,
                    reason TEXT,
                    UNIQUE(source_type, source_name, stock_code)
                )
            """)
            conn.commit()

    def _seed(self):
        with sqlite3.connect(self.db_path) as conn:
            for etype, name, desc in SEED["entities"]:
                conn.execute("INSERT OR IGNORE INTO kg_entity (entity_type, name, description) VALUES (?, ?, ?)",
                             (etype, name, desc))
            for st, sn, tt, tn, rt, w in SEED["relations"]:
                conn.execute("""
                    INSERT OR IGNORE INTO kg_relation
                        (source_type, source_name, target_type, target_name, relation_type, weight)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (st, sn, tt, tn, rt, w))
            for st, sn, _tt, code, w, reason in SEED["direct_benefit"]:
                conn.execute("""
                    INSERT OR IGNORE INTO kg_direct_benefit
                        (source_type, source_name, stock_code, weight, reason)
                    VALUES (?, ?, ?, ?, ?)
                """, (st, sn, code, w, reason))
                conn.execute("INSERT OR IGNORE INTO stock_basic (stock_code, stock_name) VALUES (?, ?)",
                             (code, _stock_name(code)))
            conn.commit()
            count = conn.execute("SELECT COUNT(*) FROM kg_direct_benefit").fetchone()[0]
            print(f"  [知识图谱] 已加载 {len(SEED['entities'])} 实体 / {len(SEED['relations'])} 关系 / {count} 直连受益")

    def search_entities(self, keywords: list, industry: str = "") -> list:
        """按关键词搜索匹配的实体"""
        terms = [k.lower() for k in keywords] + [industry.lower()]
        terms = [t for t in terms if t]
        if not terms:
            return []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            conditions = " OR ".join("(LOWER(name) LIKE ? OR LOWER(description) LIKE ?)" for _ in terms)
            params = []
            for t in terms:
                params.extend([f"%{t}%", f"%{t}%"])
            rows = conn.execute(f"SELECT * FROM kg_entity WHERE {conditions} LIMIT 20", params).fetchall()
            return [dict(r) for r in rows]

    def reason(self, keywords: list, industry: str = "", companies: list = None) -> list:
        """推理引擎：关键词+公司 → 实体 → BFS → 受益股票排序"""
        matches = self.search_entities(keywords, industry)
        # 公司实体: 直接搜索实体表
        if companies:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                placeholders = ",".join("?" for _ in companies)
                for c in companies:
                    rows = conn.execute("""
                        SELECT * FROM kg_entity
                        WHERE entity_type='company' AND name LIKE ?
                        LIMIT 1
                    """, (f"%{c}%",)).fetchall()
                    for r in rows:
                        if not any(m["entity_id"] == r["entity_id"] for m in matches):
                            matches.append(dict(r))
        if not matches:
            return []

        visited = set()
        stock_scores = defaultdict(lambda: {"paths": [], "max_weight": 0})

        for entity in matches:
            self._bfs(entity["entity_type"], entity["name"], 1.0, 0, visited, stock_scores)

        result = []
        for code, data in stock_scores.items():
            name = _stock_name(code)
            max_w = round(data["max_weight"] * 100)
            path_count = len(data["paths"])
            result.append({
                "stock_code": code,
                "stock_name": name,
                "score": max_w,
                "path_count": path_count,
                "paths": data["paths"][:3],
            })
        result.sort(key=lambda x: (-x["score"], -x["path_count"]))
        return result[:20]

    def _bfs(self, etype, ename, compound_weight, depth, visited, stock_scores):
        if depth > 4 or compound_weight < 0.05:
            return
        key = f"{etype}:{ename}"
        if key in visited:
            return
        visited.add(key)

        if etype == "stock":
            stock_scores[ename]["max_weight"] = max(stock_scores[ename]["max_weight"], compound_weight)
            stock_scores[ename]["paths"].append({
                "weight": round(compound_weight),
                "depth": depth,
            })
            return

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            # 关系边: 跳过 COMPETITOR (竞品关系不推导受益)
            rows = conn.execute("""
                SELECT target_type, target_name, relation_type, weight
                FROM kg_relation
                WHERE source_type=? AND source_name=? AND relation_type != 'COMPETITOR'
                ORDER BY weight DESC
            """, (etype, ename)).fetchall()
            direct_rows = conn.execute("""
                SELECT stock_code, weight, reason
                FROM kg_direct_benefit
                WHERE source_type=? AND source_name=?
                ORDER BY weight DESC
            """, (etype, ename)).fetchall()

        for r in rows:
            w = compound_weight * (r["weight"] / 100.0)
            self._bfs(r["target_type"], r["target_name"], w, depth + 1, visited, stock_scores)

        for r in direct_rows:
            code = r["stock_code"]
            w = compound_weight * (r["weight"] / 100.0)
            stock_scores[code]["max_weight"] = max(stock_scores[code]["max_weight"], w)
            stock_scores[code]["paths"].append({
                "weight": round(w),
                "depth": depth + 1,
                "reason": r["reason"],
            })

    def get_top_stocks(self, limit=20) -> list:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT stock_code, MAX(weight) as max_weight,
                       GROUP_CONCAT(DISTINCT source_name) as themes
                FROM kg_direct_benefit
                GROUP BY stock_code
                ORDER BY max_weight DESC
                LIMIT ?
            """, (limit,)).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["stock_name"] = _stock_name(d["stock_code"])
                d["score"] = d.pop("max_weight")
                result.append(d)
            return result


def _stock_name(code):
    names = {
        "002230": "科大讯飞", "002415": "海康威视", "688256": "寒武纪",
        "300496": "中科创达", "688088": "虹软科技",
        "601138": "工业富联", "300308": "中际旭创", "000977": "浪潮信息",
        "300502": "新易盛", "603019": "中科曙光", "688041": "海光信息",
        "300394": "天孚通信",
        "688981": "中芯国际", "002371": "北方华创", "600584": "长电科技",
        "603501": "韦尔股份", "688012": "中微公司", "301269": "华大九天",
        "002156": "通富微电", "002185": "华天科技",
        "002031": "巨轮智能", "688017": "绿的谐波", "002747": "埃斯顿",
        "300124": "汇川技术",
        "600276": "恒瑞医药", "688235": "百济神州", "603259": "药明康德",
        "300759": "康龙化成",
        "300750": "宁德时代", "601012": "隆基绿能", "002459": "晶澳科技",
        "002097": "山河智能", "300696": "爱乐达",
        "603005": "晶方科技", "300274": "阳光电源",
        "002050": "三花智控", "603728": "鸣志电器",
        "600038": "中直股份", "002023": "海特高新",
        "300424": "航新科技",
    }
    return names.get(code, code)

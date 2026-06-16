"""Theme Discovery Engine — Phase 8

从 AI 事件识别的 keywords 中发现不在主题库中的新概念，
写入 theme_candidate 表，并根据出现频率自动升级为 official。
"""
import sqlite3
from datetime import datetime


# 已知主题/实体词库，用于过滤已存在的概念
# 来源: INITIAL_THEMES keywords + kg_entity names
_KNOWN_TERMS = {
    "ai", "人工智能", "大模型", "gpt", "多模态", "神经网络",
    "算力", "光模块", "服务器", "数据中心", "cpo", "hbm",
    "半导体", "芯片", "晶圆", "封测", "eda", "光刻",
    "机器人", "人形机器人", "减速器", "伺服", "具身智能",
    "创新药", "生物药", "cxo", "临床试验", "fda",
    "先进封装", "chiplet", "sip", "3d封装", "封装",
    "灵巧手", "传感器", "执行器",
    "低空经济", "无人机", "evtol", "空管", "飞行汽车",
    "新能源", "锂电池", "光伏", "储能", "风电", "新能源汽车",
    "cpo", "光通信", "硅光", "1.6t",
    "ai芯片", "gpu", "npu", "ai加速",
    "ai服务器", "通用服务器",
    "晶圆代工", "foundry",
    "半导体设备", "刻蚀", "薄膜沉积",
    "rv减速器", "谐波减速器",
    "药物研发外包", "cdmo",
    "高速光模块", "数通",
    "gpu服务器", "训推一体",
    "电子设计自动化",
    "先进制程", "7nm", "5nm", "3nm",
    "gpu芯片", "图形处理器",
    "训练服务器", "推理服务器",
    "400g", "800g", "1.6t光模块",
    "先进封装", "sip封装",
    "机器人关节",
    "光伏组件", "逆变器", "硅片",
    "动力电池", "储能电池", "正负极",
    "空心杯电机", "精密传动",
    "电池储能", "液冷", "pcs",
    "灵巧手", "末端执行器",
    "储能系统",
    "中际旭创", "科大讯飞", "海康威视", "寒武纪", "中科创达",
    "虹软科技", "万兴科技", "工业富联", "中科曙光", "浪潮信息",
    "海光信息", "新易盛", "天孚通信", "中芯国际", "北方华创",
    "韦尔股份", "长电科技", "华大九天", "中微公司", "拓荆科技",
    "巨轮智能", "绿的谐波", "埃斯顿", "汇川技术", "拓普集团",
    "步科股份", "恒瑞医药", "百济神州", "药明康德", "康龙化成",
    "凯莱英", "通富微电", "华天科技", "晶方科技", "三花智控",
    "鸣志电器", "山河智能", "爱乐达", "中直股份", "海特高新",
    "航新科技", "宁德时代", "隆基绿能", "晶澳科技", "阳光电源",
    "中环股份", "德科立", "锐捷网络",
}


class ThemeDiscovery:
    def __init__(self, db_path=None):
        from config import Config
        self.db_path = db_path or Config.STOCKS_DB
        self._init_table()

    def _init_table(self):
        from core.db_init import init_stocks_db
        init_stocks_db()

    def _load_known_terms(self) -> set:
        known = set(_KNOWN_TERMS)
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    "SELECT LOWER(name) FROM kg_entity"
                ).fetchall()
                for r in rows:
                    known.add(r[0])
                rows = conn.execute(
                    "SELECT LOWER(theme_name) FROM theme_stock_mapping"
                ).fetchall()
                for r in rows:
                    known.add(r[0])
                rows = conn.execute(
                    "SELECT LOWER(theme_name) FROM theme_candidate WHERE status='official'"
                ).fetchall()
                for r in rows:
                    known.add(r[0])
        except Exception:
            pass
        return known

    def _calc_consecutive_days(self, theme_name: str) -> int:
        """估算连续出现天数: last_seen - first_seen 的天数跨度"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT first_seen, last_seen FROM theme_candidate WHERE theme_name=?",
                    (theme_name,)
                ).fetchone()
                if not row or not row["first_seen"] or not row["last_seen"]:
                    return 1
                from datetime import datetime
                first = datetime.fromisoformat(str(row["first_seen"]).replace(" ", "T"))
                last = datetime.fromisoformat(str(row["last_seen"]).replace(" ", "T"))
                return max(1, (last - first).days + 1)
        except Exception:
            return 1

    def discover(self, keywords: list, industry: str = ""):
        """从关键词中发现新概念候选"""
        known = self._load_known_terms()
        candidates = []
        for kw in keywords:
            k = kw.lower().strip()
            if len(k) < 2:
                continue
            if k in known:
                continue
            candidates.append(kw.strip())
        if not candidates:
            return []
        with sqlite3.connect(self.db_path) as conn:
            result = []
            for c in candidates:
                existing = conn.execute(
                    "SELECT id, mention_count, status FROM theme_candidate WHERE theme_name=?",
                    (c,)
                ).fetchone()
                if existing:
                    conn.execute("""
                        UPDATE theme_candidate
                        SET mention_count=mention_count+1, last_seen=CURRENT_TIMESTAMP
                        WHERE theme_name=?
                    """, (c,))
                    new_count = existing[1] + 1
                    if existing[2] == "candidate" and new_count >= 3:
                        conn.execute("UPDATE theme_candidate SET status='observing' WHERE theme_name=?", (c,))
                    elif existing[2] == "observing" and new_count >= 20:
                        # PRD V2: 出现次数>20 且 连续出现天数>3 → official
                        consecutive = self._calc_consecutive_days(c)
                        if consecutive > 3:
                            conn.execute("UPDATE theme_candidate SET status='official' WHERE theme_name=?", (c,))
                    result.append({"theme_name": c, "status": existing[2], "mention_count": new_count})
                else:
                    conn.execute("""
                        INSERT INTO theme_candidate (theme_name, first_seen, last_seen, mention_count, status)
                        VALUES (?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, 'candidate')
                    """, (c,))
                    result.append({"theme_name": c, "status": "candidate", "mention_count": 1})
            conn.commit()
            return result

    def get_candidates(self, status: str = None, limit: int = 50) -> list:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if status:
                rows = conn.execute("""
                    SELECT * FROM theme_candidate WHERE status=? ORDER BY mention_count DESC, last_seen DESC LIMIT ?
                """, (status, limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM theme_candidate ORDER BY mention_count DESC, last_seen DESC LIMIT ?
                """, (limit,)).fetchall()
            return [dict(r) for r in rows]

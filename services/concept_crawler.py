"""概念树爬虫 — Phase V4

从东方财富(AKShare)爬取概念板块列表和成分股，
写入 concept_board + concept_stock_member 表。

数据源:
  ak.stock_board_concept_spot_em()         → 概念板块列表(~300+)
  ak.stock_board_concept_cons_em(symbol=名称) → 单个概念的成分股
"""
import re
import sqlite3
import time
from datetime import datetime, timedelta


class ConceptCrawler:
    REFRESH_INTERVAL_DAYS = 7

    def __init__(self, db_path=None):
        from config import Config
        self.db_path = db_path or Config.STOCKS_DB
        self._init_tables()

    def _init_tables(self):
        from core.db_init import init_stocks_db
        init_stocks_db()

    # ─── 爬取概念板块列表 ───────────────────────────────

    def crawl_all_concepts(self) -> int:
        """爬取东方财富概念板块列表，写入 concept_board"""
        import akshare as ak
        try:
            df = ak.stock_board_concept_spot_em()
        except Exception as e:
            print(f"  [概念爬虫] 获取概念列表失败: {e}")
            return 0

        count = 0
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            for _, row in df.iterrows():
                name = ""
                change = 0.0
                volume = 0.0
                up = 0
                down = 0
                board_id = ""
                stock_count = 0
                for k, v in row.items():
                    k = str(k).strip()
                    if "板块名称" in k or k == "名称":
                        name = str(v)
                    elif "板块代码" in k or k == "代码":
                        board_id = str(v)
                    elif "涨跌幅" in k:
                        change = round(float(v), 2) if v else 0.0
                    elif "上涨" in k:
                        up = int(v) if v else 0
                    elif "下跌" in k:
                        down = int(v) if v else 0
                    elif "成交额" in k:
                        volume = round(float(v) / 1e8, 1) if v else 0.0
                    elif "总" in k and "市值" in k:
                        pass
                if not name:
                    continue
                # 使用概念名称作为唯一ID（东方财富板块代码不稳定）
                concept_id = name
                keywords = self._extract_keywords(name)
                conn.execute("""
                    INSERT OR REPLACE INTO concept_board
                        (concept_id, concept_name, concept_type, stock_count,
                         board_change, board_volume, up_count, down_count,
                         keywords, status, crawled_at, updated_at)
                    VALUES (?, ?, 'concept', ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                """, (concept_id, name, stock_count, change, volume,
                      up, down, keywords, now, now))
                count += 1
            conn.commit()
        print(f"  [概念爬虫] 爬取 {count} 个概念板块")
        return count

    # ─── 爬取概念成分股 ───────────────────────────────

    def crawl_concept_stocks(self, concept_name: str, concept_id: str = None) -> list:
        """爬取单个概念的成分股，写入 concept_stock_member"""
        import akshare as ak
        if concept_id is None:
            concept_id = concept_name
        try:
            df = ak.stock_board_concept_cons_em(symbol=concept_name)
        except Exception as e:
            print(f"  [概念爬虫] 获取'{concept_name}'成分股失败: {e}")
            return []

        stocks = []
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            # 清除旧成员（全量刷新）
            conn.execute("DELETE FROM concept_stock_member WHERE concept_id=?", (concept_id,))
            for _, row in df.iterrows():
                code = ""
                name = ""
                for k, v in row.items():
                    k = str(k).strip()
                    if "代码" in k:
                        code = str(v).strip()
                    elif "名称" in k:
                        name = str(v).strip()
                if not code or not name:
                    continue
                # 标准化为6位代码
                code = self._normalize_code(code)
                if not code:
                    continue
                conn.execute("""
                    INSERT OR REPLACE INTO concept_stock_member
                        (concept_id, concept_name, stock_code, stock_name, is_core, crawled_at)
                    VALUES (?, ?, ?, ?, 0, ?)
                """, (concept_id, concept_name, code, name, now))
                stocks.append({"code": code, "name": name})
            # 更新 stock_count
            conn.execute("""
                UPDATE concept_board SET stock_count=?, updated_at=?
                WHERE concept_id=?
            """, (len(stocks), now, concept_id))
            conn.commit()
        return stocks

    # ─── 全量刷新 ──────────────────────────────────────

    def refresh_all(self, force: bool = False) -> dict:
        """全量刷新: 概念列表 + 成分股。增量: 7天内不重复"""
        # 检查是否需要刷新
        if not force and not self._needs_refresh():
            print("  [概念爬虫] 概念树在7天内已刷新，跳过")
            return {"skipped": True}

        # 1. 爬取概念列表
        concept_count = self.crawl_all_concepts()
        if concept_count == 0:
            return {"concept_count": 0, "stock_count": 0}

        # 2. 获取所有活跃概念
        concepts = self._get_active_concepts()
        print(f"  [概念爬虫] 开始爬取 {len(concepts)} 个概念的成分股...")

        total_stocks = 0
        failed = 0
        for i, concept in enumerate(concepts):
            stocks = self.crawl_concept_stocks(concept["name"], concept["id"])
            total_stocks += len(stocks)
            if not stocks:
                failed += 1
            # 防封IP: 间隔0.5秒
            if i < len(concepts) - 1:
                time.sleep(0.5)
            if (i + 1) % 50 == 0:
                print(f"  [概念爬虫] 进度: {i+1}/{len(concepts)} 概念, {total_stocks} 只股票")

        print(f"  [概念爬虫] 完成: {len(concepts)} 概念, {total_stocks} 只股票, {failed} 失败")
        return {
            "skipped": False,
            "concept_count": len(concepts),
            "stock_count": total_stocks,
            "failed": failed,
        }

    # ─── 概念→关键词匹配 ────────────────────────────────

    def find_concepts_by_keyword(self, keywords: list) -> list:
        """根据关键词匹配概念，返回匹配的概念列表"""
        if not keywords:
            return []
        results = []
        seen = set()
        kw_lower = [k.lower() for k in keywords]
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            # 第1层: 精确匹配概念名
            for kw in keywords:
                rows = conn.execute(
                    "SELECT * FROM concept_board WHERE concept_name=? AND status='active'",
                    (kw,)
                ).fetchall()
                for r in rows:
                    if r["concept_id"] not in seen:
                        seen.add(r["concept_id"])
                        results.append({
                            "concept_id": r["concept_id"],
                            "concept_name": r["concept_name"],
                            "match_score": 1.0,
                            "match_method": "exact",
                        })
            # 第2层: 关键词模糊匹配
            for kw in kw_lower:
                if len(kw) < 2:
                    continue
                rows = conn.execute("""
                    SELECT * FROM concept_board
                    WHERE status='active'
                      AND (concept_name LIKE ? OR keywords LIKE ?)
                """, (f"%{kw}%", f"%{kw}%")).fetchall()
                for r in rows:
                    if r["concept_id"] not in seen:
                        seen.add(r["concept_id"])
                        results.append({
                            "concept_id": r["concept_id"],
                            "concept_name": r["concept_name"],
                            "match_score": 0.8,
                            "match_method": "keyword",
                        })
        # 按匹配分数排序
        results.sort(key=lambda x: -x["match_score"])
        return results[:10]

    def find_concepts_by_industry(self, industry: str) -> list:
        """根据行业名称匹配概念"""
        if not industry:
            return []
        results = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM concept_board
                WHERE status='active'
                  AND (concept_name LIKE ? OR keywords LIKE ?)
            """, (f"%{industry}%", f"%{industry}%")).fetchall()
            for r in rows:
                results.append({
                    "concept_id": r["concept_id"],
                    "concept_name": r["concept_name"],
                    "match_score": 0.9,
                    "match_method": "industry",
                })
        return results[:5]

    def get_concept_tree(self, limit=50) -> list:
        """返回概念树概览(概念→成分股数)"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT concept_id, concept_name, stock_count, board_change,
                       board_volume, up_count, down_count
                FROM concept_board
                WHERE status='active'
                ORDER BY stock_count DESC
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    # ─── 内部方法 ──────────────────────────────────────

    def _needs_refresh(self) -> bool:
        """检查是否需要刷新（7天内不重复）"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    "SELECT MAX(crawled_at) FROM concept_board"
                ).fetchone()
                if not row or not row[0]:
                    return True
                last = datetime.fromisoformat(str(row[0]).replace(" ", "T"))
                return (datetime.now() - last).days >= self.REFRESH_INTERVAL_DAYS
        except Exception:
            return True

    def _get_active_concepts(self) -> list:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT concept_id, concept_name FROM concept_board WHERE status='active'"
            ).fetchall()
            return [{"id": r["concept_id"], "name": r["concept_name"]} for r in rows]

    @staticmethod
    def _extract_keywords(name: str) -> str:
        """从概念名称中提取关键词"""
        # 拆分常见分隔符
        parts = re.split(r'[/、,，\-]+', name)
        keywords = [p.strip() for p in parts if len(p.strip()) >= 2]
        if not keywords:
            keywords = [name]
        return ",".join(keywords)

    @staticmethod
    def _normalize_code(code: str) -> str:
        """标准化股票代码为6位"""
        code = code.strip()
        # 去掉可能的后缀(.SZ/.SH等)
        code = re.sub(r'\.(SZ|SH|BJ)$', '', code, flags=re.IGNORECASE)
        if re.match(r'^\d{6}$', code):
            return code
        return ""

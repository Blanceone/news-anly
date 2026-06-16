"""概念树爬虫 — Phase V4 (三通道)

数据源优先级:
  1. Tushare 申万行业分类 (31 L1 + 134 L2) → 主数据源，稳定可靠
  2. 东方财富概念板块 (HTTP, ~300+) → 补充概念题材
  3. AKShare (东方财富) → 备选

写入 concept_board + concept_stock_member 表。
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

    # ─── 全量刷新 ──────────────────────────────────────

    def refresh_all(self, force: bool = False) -> dict:
        """全量刷新: 申万行业(主) + 东方财富概念(补充)。7天内不重复"""
        if not force and not self._needs_refresh():
            print("  [概念爬虫] 概念树在7天内已刷新，跳过")
            return {"skipped": True}

        now = datetime.now().isoformat()
        total_concepts = 0
        total_stocks = 0

        # ── 通道1: Tushare 申万行业分类 (主数据源) ──
        n_concepts, n_stocks = self._crawl_tushare_shenwan(now)
        total_concepts += n_concepts
        total_stocks += n_stocks
        print(f"  [概念爬虫] 申万行业: {n_concepts} 个行业, {n_stocks} 条成分股关联")

        # ── 通道2: 东方财富概念板块 (补充概念题材) ──
        n_em = self._crawl_eastmoney_concepts(now)
        if n_em > 0:
            total_concepts += n_em
            # 东方财富成分股单独爬取
            n_em_stocks = self._crawl_eastmoney_concept_stocks(now)
            total_stocks += n_em_stocks
            print(f"  [概念爬虫] 东方财富: {n_em} 个概念, {n_em_stocks} 条成分股关联")

        with sqlite3.connect(self.db_path) as conn:
            active = conn.execute(
                "SELECT COUNT(*) FROM concept_board WHERE status='active'"
            ).fetchone()[0]
            members = conn.execute(
                "SELECT COUNT(*) FROM concept_stock_member"
            ).fetchone()[0]

        print(f"  [概念爬虫] 完成: 共 {active} 个概念, {members} 条成分股关联")
        return {
            "skipped": False,
            "concept_count": active,
            "stock_count": members,
        }

    # ═══════════════════════════════════════════════════════
    #  通道1: Tushare 申万行业分类 (主数据源)
    # ═══════════════════════════════════════════════════════

    def _crawl_tushare_shenwan(self, now: str) -> tuple:
        """爬取申万行业分类 L1(31个) + L2(134个) + 成分股"""
        import tushare as ts
        from config import Config

        try:
            pro = ts.pro_api(Config.TUSHARE_TOKEN)
        except Exception as e:
            print(f"  [概念爬虫] Tushare初始化失败: {e}")
            return 0, 0

        concept_count = 0
        stock_count = 0

        with sqlite3.connect(self.db_path) as conn:
            # ── L1: 31个一级行业 ──
            try:
                l1 = pro.index_classify(level='L1', src='SW2021')
                for _, row in l1.iterrows():
                    code = row['index_code']
                    name = row['industry_name']
                    cid = f"SW1_{name}"
                    kw = self._extract_keywords(name)
                    conn.execute("""
                        INSERT OR REPLACE INTO concept_board
                            (concept_id, concept_name, concept_type, stock_count,
                             board_change, board_volume, up_count, down_count,
                             keywords, status, crawled_at, updated_at)
                        VALUES (?, ?, 'industry', 0, 0, 0, 0, 0, ?, 'active', ?, ?)
                    """, (cid, name, kw, now, now))
                    concept_count += 1
                conn.commit()
                print(f"  [概念爬虫] 申万L1: {len(l1)} 个一级行业")
            except Exception as e:
                print(f"  [概念爬虫] 申万L1获取失败: {e}")

            # ── L2: 134个二级行业 ──
            try:
                l2 = pro.index_classify(level='L2', src='SW2021')
                for _, row in l2.iterrows():
                    code = row['index_code']
                    name = row['industry_name']
                    parent = row.get('parent_code', '')
                    cid = f"SW2_{name}"
                    kw = self._extract_keywords(name)
                    conn.execute("""
                        INSERT OR REPLACE INTO concept_board
                            (concept_id, concept_name, concept_type, stock_count,
                             board_change, board_volume, up_count, down_count,
                             keywords, status, crawled_at, updated_at)
                        VALUES (?, ?, 'industry', 0, 0, 0, 0, 0, ?, 'active', ?, ?)
                    """, (cid, name, kw, now, now))
                    concept_count += 1
                conn.commit()
                print(f"  [概念爬虫] 申万L2: {len(l2)} 个二级行业")
            except Exception as e:
                print(f"  [概念爬虫] 申万L2获取失败: {e}")
                l2 = None

            # ── 成分股: 通过 index_member 获取 ──
            if l2 is not None and not l2.empty:
                industries = l2[['index_code', 'industry_name']].values.tolist()
                print(f"  [概念爬虫] 获取 {len(industries)} 个行业的成分股...")
                for i, (idx_code, idx_name) in enumerate(industries):
                    try:
                        members = pro.index_member(index_code=idx_code,
                                                   fields='index_code,con_code,is_new')
                        if members.empty:
                            continue
                        # 只取当前成分股 (is_new='Y')
                        current = members[members['is_new'] == 'Y']
                        cid = f"SW2_{idx_name}"
                        count = 0
                        for _, m in current.iterrows():
                            stock_code = self._normalize_code(str(m['con_code']))
                            if not stock_code:
                                continue
                            # 从 stock_fundamentals 获取名称
                            name_row = conn.execute(
                                "SELECT stock_name FROM stock_fundamentals WHERE stock_code=?",
                                (stock_code,)
                            ).fetchone()
                            stock_name = name_row[0] if name_row else ""
                            conn.execute("""
                                INSERT OR REPLACE INTO concept_stock_member
                                    (concept_id, concept_name, stock_code, stock_name,
                                     is_core, crawled_at)
                                VALUES (?, ?, ?, ?, 0, ?)
                            """, (cid, idx_name, stock_code, stock_name, now))
                            count += 1
                        # 更新 stock_count
                        conn.execute("""
                            UPDATE concept_board SET stock_count=?, updated_at=?
                            WHERE concept_id=?
                        """, (count, now, cid))
                        stock_count += count
                        if (i + 1) % 30 == 0:
                            print(f"  [概念爬虫] 成分股进度: {i+1}/{len(industries)}, "
                                  f"共{stock_count}条")
                        time.sleep(0.15)  # Tushare 限流
                    except Exception:
                        pass
                    conn.commit()

        return concept_count, stock_count

    # ═══════════════════════════════════════════════════════
    #  通道2: 东方财富概念板块 (补充)
    # ═══════════════════════════════════════════════════════

    def _crawl_eastmoney_concepts(self, now: str) -> int:
        """爬取东方财富概念板块列表(补充题材概念)"""
        # 方案A: AKShare
        df = None
        try:
            import akshare as ak
            df = ak.stock_board_concept_spot_em()
        except Exception:
            pass

        # 方案B: 直接HTTP
        if df is None or (hasattr(df, 'empty') and df.empty):
            df = self._crawl_concepts_direct_http()

        if df is None or (hasattr(df, 'empty') and df.empty):
            return 0

        count = 0
        with sqlite3.connect(self.db_path) as conn:
            for _, row in df.iterrows():
                name = ""
                change = 0.0
                volume = 0.0
                up = 0
                down = 0
                stock_count = 0
                for k, v in row.items():
                    k = str(k).strip()
                    if "板块名称" in k or k == "名称" or k == "name":
                        name = str(v)
                    elif "涨跌幅" in k or k == "change":
                        change = round(float(v), 2) if v else 0.0
                    elif "上涨" in k or k == "up":
                        up = int(v) if v else 0
                    elif "下跌" in k or k == "down":
                        down = int(v) if v else 0
                    elif "成交额" in k or k == "volume":
                        volume = round(float(v) / 1e8, 1) if v else 0.0
                    elif k == "stock_count":
                        stock_count = int(v) if v else 0
                if not name:
                    continue
                # 概念类用 EM_ 前缀，避免和申万行业冲突
                concept_id = f"EM_{name}"
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
        return count

    def _crawl_eastmoney_concept_stocks(self, now: str) -> int:
        """爬取东方财富概念的成分股"""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("""
                SELECT concept_id, concept_name FROM concept_board
                WHERE concept_type='concept' AND status='active'
                  AND stock_count=0
            """).fetchall()

        if not rows:
            return 0

        total = 0
        for concept_id, concept_name in rows:
            stocks = None
            # 方案A: AKShare
            try:
                import akshare as ak
                df = ak.stock_board_concept_cons_em(symbol=concept_name)
                if df is not None and not df.empty:
                    stocks = self._parse_concept_stocks(df)
            except Exception:
                pass

            # 方案B: 直接HTTP
            if stocks is None:
                stocks = self._crawl_concept_stocks_direct_http(concept_name, concept_id)

            if not stocks:
                continue

            with sqlite3.connect(self.db_path) as conn:
                for s in stocks:
                    code = self._normalize_code(s["code"])
                    if not code:
                        continue
                    conn.execute("""
                        INSERT OR REPLACE INTO concept_stock_member
                            (concept_id, concept_name, stock_code, stock_name,
                             is_core, crawled_at)
                        VALUES (?, ?, ?, ?, 0, ?)
                    """, (concept_id, concept_name, code, s["name"], now))
                conn.execute("""
                    UPDATE concept_board SET stock_count=?, updated_at=?
                    WHERE concept_id=?
                """, (len(stocks), now, concept_id))
                conn.commit()
                total += len(stocks)
            time.sleep(0.5)  # 防封IP

        return total

    # ─── 查询接口 ──────────────────────────────────────

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
        """返回概念树概览"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT concept_id, concept_name, concept_type, stock_count,
                       board_change, board_volume, up_count, down_count
                FROM concept_board
                WHERE status='active'
                ORDER BY stock_count DESC
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    # ─── 内部工具 ──────────────────────────────────────

    def _needs_refresh(self) -> bool:
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

    def _get_active_concepts(self, concept_type=None) -> list:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if concept_type:
                rows = conn.execute(
                    "SELECT concept_id, concept_name FROM concept_board "
                    "WHERE status='active' AND concept_type=?",
                    (concept_type,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT concept_id, concept_name FROM concept_board WHERE status='active'"
                ).fetchall()
            return [{"id": r["concept_id"], "name": r["concept_name"]} for r in rows]

    @staticmethod
    def _extract_keywords(name: str) -> str:
        parts = re.split(r'[/、,，\-]+', name)
        keywords = [p.strip() for p in parts if len(p.strip()) >= 2]
        if not keywords:
            keywords = [name]
        return ",".join(keywords)

    @staticmethod
    def _normalize_code(code: str) -> str:
        code = code.strip()
        code = re.sub(r'\.(SZ|SH|BJ)$', '', code, flags=re.IGNORECASE)
        if re.match(r'^\d{6}$', code):
            return code
        return ""

    def _parse_concept_stocks(self, df) -> list:
        stocks = []
        for _, row in df.iterrows():
            code, name = "", ""
            for k, v in row.items():
                k = str(k).strip()
                if "代码" in k or k == "code":
                    code = str(v).strip()
                elif "名称" in k or k == "name":
                    name = str(v).strip()
            if code and name:
                stocks.append({"code": code, "name": name})
        return stocks

    # ─── 东方财富直接HTTP ──────────────────────────────

    def _crawl_concepts_direct_http(self):
        """直接HTTP请求东方财富概念板块列表"""
        import requests
        import pandas as pd

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://quote.eastmoney.com',
        }
        url = 'https://push2.eastmoney.com/api/qt/clist/get'
        all_rows = []

        for page in range(1, 20):
            params = {
                'pn': page, 'pz': 50, 'po': 1, 'np': 1,
                'fltt': 2, 'invt': 2, 'fid': 'f3',
                'fs': 'm:90+t:3+f:!50',
                'fields': 'f2,f3,f4,f6,f8,f12,f14,f104,f105',
            }
            try:
                r = requests.get(url, params=params, headers=headers, timeout=15)
                if r.status_code != 200:
                    break
                data = r.json()
                items = data.get('data', {}).get('diff', [])
                if not items:
                    break
                for item in items:
                    all_rows.append({
                        'name': item.get('f14', ''),
                        'code': item.get('f12', ''),
                        'change': item.get('f3', 0),
                        'volume': item.get('f6', 0),
                        'up': item.get('f104', 0),
                        'down': item.get('f105', 0),
                    })
                total = data.get('data', {}).get('total', 0)
                if page * 50 >= total:
                    break
                time.sleep(0.3)
            except Exception as e:
                print(f"  [概念爬虫] 东方财富HTTP第{page}页失败: {e}")
                break

        if not all_rows:
            return None
        print(f"  [概念爬虫] 东方财富HTTP获取 {len(all_rows)} 个概念")
        return pd.DataFrame(all_rows)

    def _crawl_concept_stocks_direct_http(self, concept_name: str,
                                           concept_id: str = None) -> list:
        """直接HTTP请求概念成分股"""
        import requests

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://quote.eastmoney.com',
        }
        board_code = concept_id or concept_name
        # 去掉 EM_ 前缀取原始代码
        if board_code.startswith("EM_"):
            board_code = board_code[3:]

        url = 'https://push2.eastmoney.com/api/qt/clist/get'
        all_stocks = []
        for page in range(1, 10):
            params = {
                'pn': page, 'pz': 100, 'po': 1, 'np': 1,
                'fltt': 2, 'invt': 2, 'fid': 'f3',
                'fs': f'b:{board_code}+f:!50',
                'fields': 'f12,f14',
            }
            try:
                r = requests.get(url, params=params, headers=headers, timeout=10)
                if r.status_code != 200:
                    break
                items = r.json().get('data', {}).get('diff', [])
                if not items:
                    break
                for item in items:
                    code = str(item.get('f12', ''))
                    name = str(item.get('f14', ''))
                    if code and name:
                        all_stocks.append({"code": code, "name": name})
                total = r.json().get('data', {}).get('total', 0)
                if page * 100 >= total:
                    break
                time.sleep(0.2)
            except Exception:
                break

        return all_stocks if all_stocks else None

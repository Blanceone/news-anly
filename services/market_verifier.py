"""市场验证引擎 — Phase 6

解决"利好不涨"问题。
事件发布后，观察对应板块的市场表现：涨跌幅、成交额、上涨/下跌家数。
"""
from datetime import datetime

from services.llm_client import LLMClient
import sqlite3

# 事件行业 → A股板块名称 映射
INDUSTRY_BOARD = {
    "AI芯片": "半导体",
    "光模块": "通信",
    "服务器": "计算机设备",
    "晶圆代工": "半导体",
    "半导体设备": "半导体",
    "封测": "半导体",
    "减速器": "机械设备",
    "CXO": "医药生物",
    "先进封装": "半导体",
    "人工智能": "计算机应用",
    "半导体": "半导体",
    "机器人": "机械设备",
    "新能源": "电力设备",
    "低空经济": "国防军工",
    "创新药": "医药生物",
    "算力基础设施": "计算机应用",
    "AI": "计算机应用",
}

# 板块映射关键词（当industry未精确匹配时模糊查找）
BOARD_KEYWORDS = {
    "半导体": ["半导体", "芯片", "晶圆", "封测", "集成电路"],
    "通信": ["通信", "光模块", "5G", "CPO"],
    "计算机设备": ["服务器", "算力", "数据中心"],
    "计算机应用": ["AI", "人工智能", "大模型", "软件"],
    "机械设备": ["机器人", "减速器", "自动化", "机床"],
    "医药生物": ["医药", "药", "CXO", "临床", "创新药"],
    "电力设备": ["新能源", "光伏", "锂电", "风电", "储能"],
    "国防军工": ["军工", "低空", "无人机", "航空"],
    "电子": ["消费电子", "面板", "元器件"],
}


class MarketVerifier:
    def __init__(self, db_path=None):
        from config import Config
        self.db_path = db_path or Config.STOCKS_DB
        self.llm = LLMClient()
        self._init_table()
        self._board_cache = None
        self._board_cache_time = 0

    def _init_table(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS market_confirmation (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER NOT NULL,
                    board_name TEXT,
                    sector_change REAL,
                    volume_amount REAL,
                    up_count INTEGER,
                    down_count INTEGER,
                    confirmation_score INTEGER,
                    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def _is_trading_time(self) -> bool:
        now = datetime.now()
        if now.weekday() >= 5:
            return False
        minute = now.hour * 60 + now.minute
        return (9 * 60 + 25) <= minute <= (15 * 60)

    def _fetch_board_data(self) -> list:
        import time as _time
        now_ts = _time.time()
        if self._board_cache and (now_ts - self._board_cache_time) < 30:
            return self._board_cache
        boards = self._ts_boards()
        if not boards:
            boards = self._ak_boards()
        if boards:
            self._board_cache = boards
            self._board_cache_time = now_ts
        return boards

    def _ts_boards(self) -> list:
        """Tushare：stock_basic(industry) + daily(pct_chg) -> 行业板块聚合"""
        try:
            import tushare as ts
            from config import Config as _Cfg
            pro = ts.pro_api(_Cfg.TUSHARE_TOKEN)
            import datetime
            d = datetime.date.today()
            while d.weekday() >= 5:
                d -= datetime.timedelta(days=1)
            tdate = d.strftime("%Y%m%d")
            sb = pro.stock_basic(fields='ts_code,industry')
            daily = pro.daily(trade_date=tdate)
            chg_map = {}
            vol_map = {}
            for _, row in daily.iterrows():
                code = str(row["ts_code"])
                chg_map[code] = float(row.get("pct_chg", 0))
                vol_map[code] = float(row.get("amount", 0)) if row.get("amount") else 0
            ind_stocks = {}
            for _, row in sb.iterrows():
                ind = str(row.get("industry", "") or "").strip()
                code = str(row.get("ts_code", ""))
                if ind and code:
                    ind_stocks.setdefault(ind, []).append(code)
            boards = []
            for ind, codes in ind_stocks.items():
                changes, ups, downs, tot_vol = [], 0, 0, 0.0
                for c in codes:
                    ch = chg_map.get(c)
                    if ch is not None:
                        changes.append(ch)
                        tot_vol += vol_map.get(c, 0)
                        if ch > 0: ups += 1
                        elif ch < 0: downs += 1
                avg = round(sum(changes) / len(changes), 2) if changes else 0
                boards.append({
                    "name": ind,
                    "change": avg,
                    "up": ups,
                    "down": downs,
                    "volume": round(tot_vol / 1e8, 1),
                })
            return boards
        except Exception as e:
            print(f"  [市场验证] Tushare行业数据获取失败: {e}")
            return []

    def _ak_boards(self) -> list:
        """AKShare补充：stock_board_industry_spot_em"""
        try:
            import akshare as ak
            df = ak.stock_board_industry_spot_em()
            normalized = []
            for _, row in df.iterrows():
                entry = {}
                for k, v in row.items():
                    k = k.strip()
                    if "板块名称" in k or "名称" in k:
                        entry["name"] = str(v)
                    elif "涨跌幅" in k:
                        entry["change"] = float(v) if v else 0.0
                    elif "成交额" in k:
                        entry["volume"] = float(v) if v else 0.0
                    elif "上涨" in k:
                        entry["up"] = int(v) if v else 0
                    elif "下跌" in k:
                        entry["down"] = int(v) if v else 0
                if entry.get("name"):
                    normalized.append(entry)
            return normalized
        except Exception:
            return []

    def _resolve_board(self, industry: str, keywords: list) -> str:
        if not industry and not keywords:
            return ""
        exact = INDUSTRY_BOARD.get(industry)
        if exact:
            return exact
        all_text = f"{industry or ''} {' '.join(keywords or [])}".lower()
        for board, kws in BOARD_KEYWORDS.items():
            if any(kw in all_text for kw in kws):
                return board
        return ""

    def verify_event(self, event_id: int, industry: str, keywords: list) -> dict:
        if not self._is_trading_time():
            return {"confirmation_score": 0, "reason": "非交易时间"}

        board = self._resolve_board(industry, keywords)
        if not board:
            return {"confirmation_score": 0, "reason": "无法匹配板块"}

        boards = self._fetch_board_data()
        if not boards:
            return {"confirmation_score": 0, "reason": "行情数据不可用"}

        matched = None
        for b in boards:
            if board in b.get("name", ""):
                matched = b
                break

        if not matched:
            return {"confirmation_score": 0, "reason": f"板块[{board}]未找到"}

        change = matched.get("change", 0)
        volume = matched.get("volume", 0)
        up = matched.get("up", 0)
        down = matched.get("down", 1) or 1

        score = self._compute_score(change, volume, up, down)
        self._save(event_id, board, change, volume, up, down, score)

        ratio = f"{up}/{up+down}" if (up+down) > 0 else "N/A"
        print(f"  [市场验证] {board} 涨跌{change:+.2f}% 成交{volume/1e8:.1f}亿 涨跌比{ratio} → 评分{score}")
        return {"confirmation_score": score, "board": board, "change": change}

    def _compute_score(self, change: float, volume: float, up: int, down: int) -> int:
        total = up + down if (up + down) > 0 else 1
        up_ratio = up / total

        # 涨幅得分 (0-40)
        if change >= 5:
            change_score = 40
        elif change >= 3:
            change_score = 30
        elif change >= 1:
            change_score = 20
        elif change >= 0:
            change_score = 10
        else:
            change_score = max(0, 40 + int(change * 5))  # negative: -1% → 35, -5% → 15

        # 涨跌比得分 (0-30)
        if up_ratio >= 0.8:
            ratio_score = 30
        elif up_ratio >= 0.6:
            ratio_score = 20
        elif up_ratio >= 0.4:
            ratio_score = 10
        else:
            ratio_score = 0

        # 成交额得分 (0-30)
        vol_billion = volume / 1e8
        if vol_billion >= 500:
            vol_score = 30
        elif vol_billion >= 200:
            vol_score = 25
        elif vol_billion >= 100:
            vol_score = 20
        elif vol_billion >= 50:
            vol_score = 15
        elif vol_billion >= 20:
            vol_score = 10
        else:
            vol_score = 5

        return min(100, change_score + ratio_score + vol_score)

    def _save(self, event_id: int, board: str, change: float, volume: float,
              up: int, down: int, score: int):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO market_confirmation
                    (event_id, board_name, sector_change, volume_amount,
                     up_count, down_count, confirmation_score)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (event_id, board, change, volume, up, down, score))
            conn.commit()

    def get_confirmation(self, event_id: int) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("""
                SELECT * FROM market_confirmation WHERE event_id=? ORDER BY id DESC LIMIT 1
            """, (event_id,)).fetchone()
            return dict(row) if row else {}

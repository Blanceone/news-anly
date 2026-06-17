"""测试资金异动检测器

Spec 7: 测试AKShare接口调用的网络异常处理及数据清洗逻辑
"""
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock

from core.db_init import init_concept_db


class TestCapitalDetector(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.concept_fd, cls.concept_db = tempfile.mkstemp(suffix=".db")
        os.close(cls.concept_fd)

        import config
        config.Config.CONCEPT_DB = cls.concept_db

        init_concept_db()

    @classmethod
    def tearDownClass(cls):
        try:
            os.unlink(cls.concept_db)
        except Exception:
            pass

    def setUp(self):
        with sqlite3.connect(self.concept_db) as conn:
            for t in ("limitup_stats", "capital_anomaly", "dragon_tiger",
                       "northbound_flow", "concept_stock", "concept_candidate"):
                conn.execute(f"DELETE FROM {t}")
            conn.commit()

    def test_aggregate_limitup_empty_when_no_data(self):
        """涨停聚合: 无数据时返回空"""
        from services.capital_detector import CapitalDetector
        cd = CapitalDetector(concept_db=self.concept_db)
        # Mock AKShare 返回空
        with patch("services.capital_detector.CapitalDetector.get_limitup_pool", return_value=[]):
            result = cd.aggregate_limitup_by_concept("20250101")
        self.assertEqual(result, [])

    def test_aggregate_limitup_maps_to_concepts(self):
        """涨停聚合: 涨停股正确映射到概念"""
        # 创建概念和股票映射
        with sqlite3.connect(self.concept_db) as conn:
            conn.execute("""
                INSERT INTO concept_candidate (standard_name, status, mention_count, last_mention_date)
                VALUES ('测试概念', 'observing', 5, date('now'))
            """)
            cid = conn.execute("SELECT id FROM concept_candidate WHERE standard_name='测试概念'").fetchone()[0]
            conn.execute("""
                INSERT INTO concept_stock (concept_id, stock_code, role, is_target)
                VALUES (?, '000001', 'leader', 1)
            """, (cid,))
            conn.commit()

        from services.capital_detector import CapitalDetector
        cd = CapitalDetector(concept_db=self.concept_db)

        mock_limitups = [
            {"stock_code": "000001", "stock_name": "测试股", "industry": "科技",
             "consecutive": 3, "trade_date": "20250101"},
        ]
        with patch.object(cd, "get_limitup_pool", return_value=mock_limitups):
            result = cd.aggregate_limitup_by_concept("20250101")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["limitup_count"], 1)

    def test_save_dragon_tiger(self):
        """龙虎榜数据正确写入"""
        from services.capital_detector import CapitalDetector
        cd = CapitalDetector(concept_db=self.concept_db)

        records = [{
            "trade_date": "2025-01-01",
            "stock_code": "000001",
            "buyer_name": "机构专用",
            "net_buy": 5000.0,
            "buyer_type": "institution",
        }]
        cd._save_dragon_tiger(records)

        with sqlite3.connect(self.concept_db) as conn:
            row = conn.execute(
                "SELECT * FROM dragon_tiger WHERE stock_code='000001'"
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[4], 5000.0)  # net_buy

    def test_classify_buyer(self):
        """买方分类: 机构/游资/散户"""
        from services.capital_detector import CapitalDetector
        cd = CapitalDetector(concept_db=self.concept_db)

        self.assertEqual(cd._classify_buyer("机构专用"), "institution")
        self.assertEqual(cd._classify_buyer("东方财富拉萨团结路"), "hot_money")
        self.assertEqual(cd._classify_buyer("普通营业部"), "retail")

    def test_save_northbound(self):
        """北向资金数据正确写入"""
        from services.capital_detector import CapitalDetector
        cd = CapitalDetector(concept_db=self.concept_db)

        records = [
            {"trade_date": "2025-01-01", "stock_code": "000001", "net_buy": 1000.0},
            {"trade_date": "2025-01-01", "stock_code": "000002", "net_buy": -500.0},
        ]
        cd._save_northbound(records)

        with sqlite3.connect(self.concept_db) as conn:
            rows = conn.execute(
                "SELECT * FROM northbound_flow WHERE trade_date='2025-01-01'"
            ).fetchall()
        self.assertEqual(len(rows), 2)

    def test_detect_anomalies_volume_breakout(self):
        """资金异动: 涨停>=5只时生成 volume_breakout"""
        today = datetime.now().strftime("%Y-%m-%d")
        with sqlite3.connect(self.concept_db) as conn:
            conn.execute("""
                INSERT INTO concept_candidate (standard_name, status, mention_count, last_mention_date)
                VALUES ('异动概念', 'observing', 5, date('now'))
            """)
            cid = conn.execute("SELECT id FROM concept_candidate WHERE standard_name='异动概念'").fetchone()[0]
            conn.execute("""
                INSERT INTO limitup_stats (trade_date, concept_id, limitup_count, max_consecutive_boards)
                VALUES (?, ?, 8, 3)
            """, (today, cid))
            conn.commit()

        from services.capital_detector import CapitalDetector
        cd = CapitalDetector(concept_db=self.concept_db)
        anomalies = cd.detect_anomalies()

        breakout = [a for a in anomalies if a["anomaly_type"] == "volume_breakout"]
        self.assertGreater(len(breakout), 0)


if __name__ == "__main__":
    unittest.main()

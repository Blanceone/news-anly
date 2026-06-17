"""测试资金异动检测器"""
import os
import sqlite3
import tempfile
import unittest

TEST_DB = os.path.join(tempfile.gettempdir(), "test_capital.db")


def setup_test_db():
    from config import Config
    Config.CONCEPT_DB = TEST_DB
    from core.db_init import init_concept_db
    init_concept_db()


def cleanup():
    if os.path.exists(TEST_DB):
        os.unlink(TEST_DB)


class TestCapitalDetector(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cleanup()
        setup_test_db()

    @classmethod
    def tearDownClass(cls):
        cleanup()

    def test_import(self):
        from services.capital_detector import CapitalDetector
        cd = CapitalDetector()
        self.assertIsNotNone(cd)

    def test_fetch_limitup_no_token(self):
        from services.capital_detector import CapitalDetector
        from config import Config
        old_token = Config.TUSHARE_TOKEN
        Config.TUSHARE_TOKEN = ""
        cd = CapitalDetector()
        result = cd.fetch_limitup()
        self.assertEqual(result, [])
        Config.TUSHARE_TOKEN = old_token

    def test_save_anomalies(self):
        from services.capital_detector import CapitalDetector
        cd = CapitalDetector()
        anomalies = [{
            "anomaly_type": "volume_breakout",
            "concept_id": "CPT_test",
            "stock_code": "",
            "stock_name": "",
            "amount": 5,
            "detail": "测试异动",
            "trade_date": "20250101",
        }]
        cd._save_anomalies(anomalies)
        with sqlite3.connect(TEST_DB) as conn:
            count = conn.execute("SELECT COUNT(*) FROM capital_anomaly").fetchone()[0]
        self.assertEqual(count, 1)

    def test_get_recent_anomalies(self):
        from services.capital_detector import CapitalDetector
        cd = CapitalDetector()
        result = cd.get_recent_anomalies(48)
        self.assertIsInstance(result, list)

    def test_aggregate_limitup_empty(self):
        from services.capital_detector import CapitalDetector
        cd = CapitalDetector()
        # 没有涨停数据时应该返回空列表
        result = cd.aggregate_limitup_by_concept("20990101")
        self.assertEqual(result, [])

    def test_detect_anomalies(self):
        from services.capital_detector import CapitalDetector
        cd = CapitalDetector()
        result = cd.detect_anomalies()
        self.assertIsInstance(result, list)


if __name__ == "__main__":
    unittest.main()

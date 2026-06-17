"""测试风控引擎"""
import os
import sqlite3
import tempfile
import unittest

TEST_DB = os.path.join(tempfile.gettempdir(), "test_risk.db")
TEST_NEWS_DB = os.path.join(tempfile.gettempdir(), "test_risk_news.db")


def setup_test_db():
    from config import Config
    Config.CONCEPT_DB = TEST_DB
    Config.NEWS_DB = TEST_NEWS_DB
    from core.db_init import init_concept_db, init_news_db
    init_concept_db()
    init_news_db()


def cleanup():
    for f in (TEST_DB, TEST_NEWS_DB):
        if os.path.exists(f):
            os.unlink(f)


class TestRiskControl(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cleanup()
        setup_test_db()
        cls._seed_test_data()

    @classmethod
    def tearDownClass(cls):
        cleanup()

    @classmethod
    def _seed_test_data(cls):
        with sqlite3.connect(TEST_DB) as conn:
            conn.execute("""
                INSERT INTO concept_candidate
                    (concept_id, concept_name, status, lifecycle,
                     mention_count, mention_days, signal_count)
                VALUES
                    ('CPT_risk001', '风控测试A', 'validated', 'GROWING', 8, 4, 6),
                    ('CPT_risk002', '风控测试B', 'candidate', 'DECLINING', 2, 1, 1)
            """)
            conn.execute("""
                INSERT INTO concept_event
                    (concept_id, event_id, event_type, event_score, news_title)
                VALUES ('CPT_risk001', 1, 'POLICY', 80, '风控测试新闻')
            """)
            conn.commit()

    def test_import(self):
        from services.risk_control import RiskControl
        rc = RiskControl()
        self.assertIsNotNone(rc)

    def test_check_event_support_pass(self):
        from services.risk_control import RiskControl
        rc = RiskControl()
        result = rc._check_event_support("CPT_risk001")
        self.assertTrue(result["is_passed"])

    def test_check_event_support_fail(self):
        from services.risk_control import RiskControl
        rc = RiskControl()
        result = rc._check_event_support("CPT_risk002")
        self.assertFalse(result["is_passed"])

    def test_check_chase_high_growing(self):
        from services.risk_control import RiskControl
        rc = RiskControl()
        result = rc._check_chase_high("CPT_risk001")
        self.assertTrue(result["is_passed"])

    def test_check_chase_high_declining(self):
        from services.risk_control import RiskControl
        rc = RiskControl()
        result = rc._check_chase_high("CPT_risk002")
        self.assertFalse(result["is_passed"])
        self.assertIn("DECLINING", result["detail"])

    def test_check_stop_loss(self):
        from services.risk_control import RiskControl
        rc = RiskControl()
        result = rc._check_stop_loss("CPT_risk001")
        self.assertTrue(result["is_passed"])

    def test_check_all(self):
        from services.risk_control import RiskControl
        rc = RiskControl()
        result = rc.check_all("CPT_risk001")
        self.assertIn("checks", result)
        self.assertIn("risk_level", result)
        self.assertIn("summary", result)

    def test_build_summary(self):
        from services.risk_control import RiskControl
        rc = RiskControl()
        checks = {
            "event_support": {"is_passed": True},
            "volume": {"is_passed": False},
        }
        summary = rc._build_summary(checks)
        self.assertIn("OK", summary)
        self.assertIn("FAIL", summary)

    def test_get_risk_summary(self):
        from services.risk_control import RiskControl
        rc = RiskControl()
        # 先执行一次 check_all 生成数据
        rc.check_all("CPT_risk001")
        summary = rc.get_risk_summary()
        self.assertIsInstance(summary, list)


if __name__ == "__main__":
    unittest.main()

"""测试7信号验证引擎"""
import os
import sqlite3
import tempfile
import unittest

TEST_DB = os.path.join(tempfile.gettempdir(), "test_validator.db")
TEST_NEWS_DB = os.path.join(tempfile.gettempdir(), "test_validator_news.db")


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


class TestConceptValidator(unittest.TestCase):
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
        """插入测试概念和事件"""
        with sqlite3.connect(TEST_DB) as conn:
            conn.execute("""
                INSERT INTO concept_candidate
                    (concept_id, concept_name, status, mention_count, mention_days, lifecycle)
                VALUES ('CPT_test001', '测试概念A', 'observing', 5, 3, 'GROWING')
            """)
            conn.execute("""
                INSERT INTO concept_event
                    (concept_id, event_id, event_type, event_score, news_title)
                VALUES ('CPT_test001', 1, 'POLICY', 80, '测试新闻标题')
            """)
            conn.execute("""
                INSERT INTO concept_stock
                    (concept_id, stock_code, stock_name, role, benefit_path, is_core)
                VALUES ('CPT_test001', '000001.SZ', '测试股票A', 'leader', '核心供应商', 1)
            """)
            conn.commit()

    def test_import(self):
        from services.concept_validator import ConceptValidator
        cv = ConceptValidator()
        self.assertIsNotNone(cv)

    def test_signal_1_source_event(self):
        from services.concept_validator import ConceptValidator
        cv = ConceptValidator()
        result = cv._signal_1_source_event("CPT_test001")
        self.assertTrue(result["is_met"])
        self.assertIn("1个事件", result["evidence"])

    def test_signal_1_no_event(self):
        from services.concept_validator import ConceptValidator
        cv = ConceptValidator()
        result = cv._signal_1_source_event("CPT_nonexist")
        self.assertFalse(result["is_met"])

    def test_signal_3_limitup(self):
        from services.concept_validator import ConceptValidator
        cv = ConceptValidator()
        result = cv._signal_3_limitup("CPT_test001")
        self.assertIsInstance(result["is_met"], bool)

    def test_signal_5_upstream_downstream(self):
        from services.concept_validator import ConceptValidator
        cv = ConceptValidator()
        result = cv._signal_5_upstream_downstream("CPT_test001")
        # 只有1只股票1个角色, 应该不满足
        self.assertFalse(result["is_met"])

    def test_signal_6_media_heat(self):
        from services.concept_validator import ConceptValidator
        cv = ConceptValidator()
        result = cv._signal_6_media_heat("CPT_test001")
        self.assertIsInstance(result["is_met"], bool)

    def test_validate(self):
        from services.concept_validator import ConceptValidator
        cv = ConceptValidator()
        result = cv.validate("CPT_test001")
        self.assertIn("signals", result)
        self.assertIn("verdict", result)
        self.assertIn("signal_count", result)
        self.assertGreaterEqual(result["signal_count"], 1)  # 至少有信号1

    def test_determine_verdict_main_concept(self):
        from services.concept_validator import ConceptValidator
        cv = ConceptValidator()
        signals = {i: {"is_met": True} for i in range(1, 8)}
        verdict = cv._determine_verdict(7, signals)
        self.assertEqual(verdict["verdict"], "main_concept")
        self.assertEqual(verdict["action"], "participate")

    def test_determine_verdict_one_day_wonder(self):
        from services.concept_validator import ConceptValidator
        cv = ConceptValidator()
        signals = {1: {"is_met": True}, 2: {"is_met": False}, 3: {"is_met": True}}
        for i in range(4, 8):
            signals[i] = {"is_met": False}
        verdict = cv._determine_verdict(2, signals)
        self.assertEqual(verdict["verdict"], "one_day_wonder")
        self.assertEqual(verdict["action"], "avoid")

    def test_determine_verdict_no_source_event(self):
        from services.concept_validator import ConceptValidator
        cv = ConceptValidator()
        signals = {1: {"is_met": False}}
        for i in range(2, 8):
            signals[i] = {"is_met": True}
        verdict = cv._determine_verdict(6, signals)
        self.assertEqual(verdict["verdict"], "one_day_wonder")


if __name__ == "__main__":
    unittest.main()

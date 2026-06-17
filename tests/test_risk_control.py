"""测试风控引擎

Spec: 风控红线检查 — chasing_high / no_event_support / low_volume
"""
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime

from core.db_init import init_concept_db


class TestRiskControl(unittest.TestCase):
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
            for t in ("risk_check", "concept_score", "concept_event",
                       "concept_candidate"):
                conn.execute(f"DELETE FROM {t}")
            conn.commit()

    def _insert_concept(self, name):
        today = datetime.now().strftime("%Y-%m-%d")
        with sqlite3.connect(self.concept_db) as conn:
            conn.execute("""
                INSERT INTO concept_candidate (standard_name, status, mention_count, last_mention_date)
                VALUES (?, 'validated', 5, ?)
            """, (name, today))
            conn.commit()
            return conn.execute(
                "SELECT id FROM concept_candidate WHERE standard_name=?", (name,)
            ).fetchone()[0]

    def test_event_support_pass_when_events_exist(self):
        """事件支撑: 有事件时通过"""
        cid = self._insert_concept("有事件概念")
        today = datetime.now().strftime("%Y-%m-%d")

        with sqlite3.connect(self.concept_db) as conn:
            conn.execute("""
                INSERT INTO concept_event (concept_id, event_id, trade_date)
                VALUES (?, 1, ?)
            """, (cid, today))
            conn.commit()

        from services.risk_control import RiskControl
        rc = RiskControl(concept_db=self.concept_db)
        result = rc.check_all(cid, today)

        self.assertTrue(result["checks"]["no_event_support"]["is_passed"])

    def test_event_support_fail_when_no_events(self):
        """事件支撑: 无事件时不通过"""
        cid = self._insert_concept("无事件概念")
        today = datetime.now().strftime("%Y-%m-%d")

        from services.risk_control import RiskControl
        rc = RiskControl(concept_db=self.concept_db)
        result = rc.check_all(cid, today)

        self.assertFalse(result["checks"]["no_event_support"]["is_passed"])

    def test_chase_high_fail_for_one_day_wonder(self):
        """追高风险: verdict=one_day_wonder时不通过"""
        cid = self._insert_concept("一日游概念")
        today = datetime.now().strftime("%Y-%m-%d")

        with sqlite3.connect(self.concept_db) as conn:
            conn.execute("""
                INSERT INTO concept_score (concept_id, trade_date, signal_count, verdict)
                VALUES (?, ?, 2, 'one_day_wonder')
            """, (cid, today))
            conn.commit()

        from services.risk_control import RiskControl
        rc = RiskControl(concept_db=self.concept_db)
        result = rc.check_all(cid, today)

        self.assertFalse(result["checks"]["chasing_high"]["is_passed"])

    def test_chase_high_pass_for_main_concept(self):
        """追高风险: verdict=main_concept时通过"""
        cid = self._insert_concept("主线概念")
        today = datetime.now().strftime("%Y-%m-%d")

        with sqlite3.connect(self.concept_db) as conn:
            conn.execute("""
                INSERT INTO concept_score (concept_id, trade_date, signal_count, verdict)
                VALUES (?, ?, 6, 'main_concept')
            """, (cid, today))
            conn.commit()

        from services.risk_control import RiskControl
        rc = RiskControl(concept_db=self.concept_db)
        result = rc.check_all(cid, today)

        self.assertTrue(result["checks"]["chasing_high"]["is_passed"])

    def test_risk_check_saved_to_db(self):
        """风控检查结果正确写入 risk_check 表"""
        cid = self._insert_concept("入库测试")
        today = datetime.now().strftime("%Y-%m-%d")

        from services.risk_control import RiskControl
        rc = RiskControl(concept_db=self.concept_db)
        rc.check_all(cid, today)

        with sqlite3.connect(self.concept_db) as conn:
            rows = conn.execute(
                "SELECT * FROM risk_check WHERE concept_id=? AND trade_date=?",
                (cid, today)
            ).fetchall()
        self.assertEqual(len(rows), 3)  # 3个检查项

    def test_is_safe_when_all_pass(self):
        """所有检查通过时 is_safe=True"""
        cid = self._insert_concept("安全概念")
        today = datetime.now().strftime("%Y-%m-%d")

        # 添加事件
        with sqlite3.connect(self.concept_db) as conn:
            conn.execute("""
                INSERT INTO concept_event (concept_id, event_id, trade_date)
                VALUES (?, 1, ?)
            """, (cid, today))
            # 添加main_concept评分
            conn.execute("""
                INSERT INTO concept_score (concept_id, trade_date, signal_count, verdict)
                VALUES (?, ?, 6, 'main_concept')
            """, (cid, today))
            conn.commit()

        from services.risk_control import RiskControl
        rc = RiskControl(concept_db=self.concept_db)

        # Mock market monitor
        from unittest.mock import patch
        with patch("services.risk_control.RiskControl._check_market_volume",
                   return_value={"is_passed": True, "detail": "mock: 量能健康"}):
            result = rc.check_all(cid, today)

        self.assertTrue(result["is_safe"])
        self.assertEqual(result["risk_level"], "low")


if __name__ == "__main__":
    unittest.main()

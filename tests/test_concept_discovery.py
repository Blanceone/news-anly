"""测试概念发现引擎"""
import os
import sqlite3
import tempfile
import unittest

# 使用临时数据库
TEST_DB = os.path.join(tempfile.gettempdir(), "test_concept.db")
TEST_NEWS_DB = os.path.join(tempfile.gettempdir(), "test_news.db")


def setup_test_db():
    """初始化测试数据库"""
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


class TestConceptDiscovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cleanup()
        setup_test_db()

    @classmethod
    def tearDownClass(cls):
        cleanup()

    def test_import(self):
        from services.concept_discovery import ConceptDiscovery
        cd = ConceptDiscovery()
        self.assertIsNotNone(cd)

    def test_make_concept_id(self):
        from services.concept_discovery import ConceptDiscovery
        cd = ConceptDiscovery()
        cid = cd._make_concept_id("低空经济")
        self.assertTrue(cid.startswith("CPT_"))
        self.assertEqual(len(cid), 12)  # CPT_ + 8 hex chars

    def test_make_concept_id_deterministic(self):
        from services.concept_discovery import ConceptDiscovery
        cd = ConceptDiscovery()
        id1 = cd._make_concept_id("固态电池")
        id2 = cd._make_concept_id("固态电池")
        self.assertEqual(id1, id2)

    def test_infer_type(self):
        from services.concept_discovery import ConceptDiscovery
        cd = ConceptDiscovery()
        self.assertEqual(cd._infer_type("POLICY"), "policy")
        self.assertEqual(cd._infer_type("TECHNOLOGY"), "tech")
        self.assertEqual(cd._infer_type("OTHER"), "general")

    def test_looks_like_concept(self):
        from services.concept_discovery import ConceptDiscovery
        cd = ConceptDiscovery()
        self.assertTrue(cd._looks_like_concept("低空经济"))
        self.assertTrue(cd._looks_like_concept("固态电池"))
        self.assertFalse(cd._looks_like_concept("增长"))
        self.assertFalse(cd._looks_like_concept("利润"))

    def test_extract_concepts_from_event(self):
        from services.concept_discovery import ConceptDiscovery
        cd = ConceptDiscovery()
        event = {
            "importance": "S",
            "industry": "新能源",
            "sub_industry": "固态电池",
            "concept_keywords": ["固态电池", "锂电池"],
            "keywords_json": '["固态电池", "电解质"]',
            "event_type": "TECHNOLOGY",
        }
        concepts = cd._extract_concepts_from_event(event)
        self.assertIn("固态电池", concepts)
        self.assertIn("新能源", concepts)
        self.assertIn("锂电池", concepts)

    def test_upsert_concept(self):
        from services.concept_discovery import ConceptDiscovery
        cd = ConceptDiscovery()
        event = {
            "_event_id": 1,
            "event_type": "POLICY",
            "importance": "A",
            "industry": "人工智能",
            "keywords_json": "[]",
        }
        cid = cd._upsert_concept("数据要素", event)
        self.assertTrue(cid.startswith("CPT_"))

        # 验证入库
        with sqlite3.connect(TEST_DB) as conn:
            row = conn.execute(
                "SELECT concept_name, status, mention_count FROM concept_candidate WHERE concept_id=?",
                (cid,)
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "数据要素")
        self.assertEqual(row[1], "candidate")
        self.assertEqual(row[2], 1)

    def test_upsert_concept_increment(self):
        from services.concept_discovery import ConceptDiscovery
        cd = ConceptDiscovery()
        event = {"_event_id": 2, "event_type": "POLICY", "importance": "A",
                 "industry": "", "keywords_json": "[]"}
        cid = cd._upsert_concept("数据要素", event)
        with sqlite3.connect(TEST_DB) as conn:
            row = conn.execute(
                "SELECT mention_count FROM concept_candidate WHERE concept_id=?",
                (cid,)
            ).fetchone()
        self.assertEqual(row[0], 2)

    def test_check_upgrades_candidate_to_observing(self):
        from services.concept_discovery import ConceptDiscovery
        cd = ConceptDiscovery()
        # 插入一个新的候选概念并设置满足升级条件
        with sqlite3.connect(TEST_DB) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO concept_candidate
                    (concept_id, concept_name, status, mention_count, mention_days, lifecycle)
                VALUES ('CPT_upgrade_test', '升级测试概念', 'candidate', 5, 3, 'BIRTH')
            """)
            conn.commit()
        upgrades = cd.check_upgrades()
        names = [u["concept_name"] for u in upgrades]
        self.assertIn("升级测试概念", names)

    def test_get_concepts(self):
        from services.concept_discovery import ConceptDiscovery
        cd = ConceptDiscovery()
        concepts = cd.get_concepts()
        self.assertIsInstance(concepts, list)


if __name__ == "__main__":
    unittest.main()

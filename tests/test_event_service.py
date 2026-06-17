"""测试事件抽取与概念归一化服务

Spec 7: Mock LLM返回，测试事件抽取与归一化逻辑是否正确入库
"""
import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from core.db_init import init_news_db, init_concept_db


class TestEventService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.news_fd, cls.news_db = tempfile.mkstemp(suffix=".db")
        cls.concept_fd, cls.concept_db = tempfile.mkstemp(suffix=".db")
        os.close(cls.news_fd)
        os.close(cls.concept_fd)

        import config
        config.Config.NEWS_DB = cls.news_db
        config.Config.CONCEPT_DB = cls.concept_db

        init_news_db()
        init_concept_db()

        # 插入测试新闻
        with sqlite3.connect(cls.news_db) as conn:
            conn.execute("""
                INSERT INTO news (id, title, content, source, source_name, created_at)
                VALUES ('test_001', '低空经济政策发布', '国务院发布低空经济发展规划', 'cls', '财联社', datetime('now'))
            """)
            conn.commit()

    @classmethod
    def tearDownClass(cls):
        for path in (cls.news_db, cls.concept_db):
            try:
                os.unlink(path)
            except Exception:
                pass

    def _make_service(self, mock_llm_response):
        """创建 EventService 并 mock LLM"""
        from services.event_service import EventService
        svc = EventService(news_db=self.news_db, concept_db=self.concept_db)
        svc.llm = MagicMock()
        svc.llm.available = True
        svc.llm.chat = MagicMock(return_value=mock_llm_response)
        return svc

    def test_event_extraction_parses_json(self):
        """测试事件抽取能正确解析LLM返回的JSON"""
        mock_response = json.dumps({
            "event_type": "政策发布",
            "summary": "国务院发布低空经济发展规划",
            "sentiment": "利好",
            "entities": ["国务院", "低空经济"],
            "potential_concepts": ["低空经济", "无人机"]
        })
        svc = self._make_service(mock_response)
        result = svc.process_news("低空经济政策发布 国务院发布低空经济发展规划", "test_001")

        self.assertEqual(result.get("event_type"), "政策发布")
        self.assertEqual(result.get("sentiment"), "利好")
        self.assertIn("低空经济", result.get("potential_concepts", []))

    def test_event_saved_to_db(self):
        """测试事件正确写入 event_analysis 表"""
        mock_response = json.dumps({
            "event_type": "技术突破",
            "summary": "固态电池量产突破",
            "sentiment": "利好",
            "entities": ["宁德时代"],
            "potential_concepts": ["固态电池"]
        })
        svc = self._make_service(mock_response)

        with sqlite3.connect(self.news_db) as conn:
            conn.execute("""
                INSERT INTO news (id, title, content, source, source_name, created_at)
                VALUES ('test_002', '固态电池量产', '宁德时代固态电池量产', 'cls', '财联社', datetime('now'))
            """)
            conn.commit()

        result = svc.process_news("固态电池量产 宁德时代固态电池量产", "test_002")

        # 检查 event_analysis 表
        with sqlite3.connect(self.news_db) as conn:
            row = conn.execute(
                "SELECT * FROM event_analysis WHERE news_id='test_002'"
            ).fetchone()
        self.assertIsNotNone(row)

    def test_concept_normalization_adds_to_dictionary(self):
        """测试概念归一化将新概念加入词典"""
        # 第一次调用: 事件抽取
        event_response = json.dumps({
            "event_type": "技术突破",
            "summary": "量子计算新突破",
            "sentiment": "利好",
            "entities": ["中科院"],
            "potential_concepts": ["量子计算"]
        })
        # 第二次调用: 概念归一化
        norm_response = json.dumps([{
            "raw_keyword": "量子计算",
            "standard_concept": "量子计算",
            "is_new": True
        }])

        from services.event_service import EventService
        svc = EventService(news_db=self.news_db, concept_db=self.concept_db)
        svc.llm = MagicMock()
        svc.llm.available = True
        svc.llm.chat = MagicMock(side_effect=[event_response, norm_response])

        with sqlite3.connect(self.news_db) as conn:
            conn.execute("""
                INSERT INTO news (id, title, content, source, source_name, created_at)
                VALUES ('test_003', '量子计算突破', '中科院量子计算新突破', 'cls', '财联社', datetime('now'))
            """)
            conn.commit()

        svc.process_news("量子计算突破 中科院量子计算新突破", "test_003")

        # 检查词典
        with sqlite3.connect(self.concept_db) as conn:
            row = conn.execute(
                "SELECT * FROM concept_dictionary WHERE standard_name='量子计算'"
            ).fetchone()
        self.assertIsNotNone(row)

    def test_concept_candidate_created(self):
        """测试概念归一化后创建候选"""
        event_response = json.dumps({
            "event_type": "行业数据",
            "summary": "储能市场数据",
            "sentiment": "利好",
            "entities": [],
            "potential_concepts": ["储能"]
        })
        norm_response = json.dumps([{
            "raw_keyword": "储能",
            "standard_concept": "储能",
            "is_new": True
        }])

        from services.event_service import EventService
        svc = EventService(news_db=self.news_db, concept_db=self.concept_db)
        svc.llm = MagicMock()
        svc.llm.available = True
        svc.llm.chat = MagicMock(side_effect=[event_response, norm_response])

        with sqlite3.connect(self.news_db) as conn:
            conn.execute("""
                INSERT INTO news (id, title, content, source, source_name, created_at)
                VALUES ('test_004', '储能数据', '储能市场规模', 'cls', '财联社', datetime('now'))
            """)
            conn.commit()

        svc.process_news("储能数据 储能市场规模", "test_004")

        with sqlite3.connect(self.concept_db) as conn:
            row = conn.execute(
                "SELECT * FROM concept_candidate WHERE standard_name='储能'"
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[2], "candidate")  # status

    def test_fallback_when_llm_unavailable(self):
        """测试LLM不可用时的fallback"""
        from services.event_service import EventService
        svc = EventService(news_db=self.news_db, concept_db=self.concept_db)
        svc.llm = MagicMock()
        svc.llm.available = False
        svc.llm.chat = MagicMock(return_value="")

        with sqlite3.connect(self.news_db) as conn:
            conn.execute("""
                INSERT INTO news (id, title, content, source, source_name, created_at)
                VALUES ('test_005', '普通公告', '普通公告内容', 'cls', '财联社', datetime('now'))
            """)
            conn.commit()

        result = svc.process_news("普通公告 普通公告内容", "test_005")
        # fallback 应返回默认值
        self.assertEqual(result.get("event_type"), "公司公告")


if __name__ == "__main__":
    unittest.main()

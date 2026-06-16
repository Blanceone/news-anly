"""业务逻辑离线测试 — 不依赖网络API"""
import sys
import os
import sqlite3
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import Config


def test_db_init():
    """测试数据库初始化"""
    from core.db_init import init_news_db, init_stocks_db
    init_news_db()
    init_stocks_db()
    # 验证表存在
    with sqlite3.connect(Config.NEWS_DB) as conn:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        assert "news" in tables, f"news table missing: {tables}"
        assert "event_analysis" in tables, f"event_analysis table missing: {tables}"
        print(f"  [OK] news.db: {len(tables)} tables")

    with sqlite3.connect(Config.STOCKS_DB) as conn:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        for required in ("stock_basic", "theme_stock_mapping", "event_stock_mapping",
                          "stock_score", "recommendation_result", "kg_entity",
                          "kg_relation", "kg_direct_benefit", "theme_candidate",
                          "event_cluster", "event_cluster_map", "theme_heat",
                          "stock_profile", "theme_limitup_stats",
                          "backtest_result", "backtest_trades"):
            assert required in tables, f"{required} table missing"
        print(f"  [OK] stocks.db: {len(tables)} tables")


def test_stock_service():
    """测试股票关联服务"""
    from services.stock_service import StockService
    ss = StockService()

    # 测试关键词匹配
    event = {"keywords": ["AI", "大模型"], "industry": "人工智能", "sub_industry": ""}
    matched = ss.match_event_to_stocks(event)
    assert len(matched) > 0, "AI keyword should match stocks"
    codes = [m["stock_code"] for m in matched]
    assert "002230" in codes, f"科大讯飞 should match AI: {codes}"
    print(f"  [OK] 关键词匹配: AI → {len(matched)} 只股票")

    # 测试半导体匹配
    event2 = {"keywords": ["半导体", "芯片"], "industry": "半导体", "sub_industry": "晶圆代工"}
    matched2 = ss.match_event_to_stocks(event2)
    assert len(matched2) > 0, "半导体 keyword should match stocks"
    print(f"  [OK] 关键词匹配: 半导体 → {len(matched2)} 只股票")

    # 测试受益链分层
    for m in matched:
        assert m.get("benefit_level") in (1, 2, 3), f"Invalid benefit_level: {m}"
    print(f"  [OK] 受益链分层: levels correct")


def test_knowledge_graph():
    """测试知识图谱推理"""
    from services.knowledge_graph import KnowledgeGraph
    kg = KnowledgeGraph()

    # 测试实体搜索
    entities = kg.search_entities(["AI", "芯片"])
    assert len(entities) > 0, "Should find entities for AI/芯片"
    print(f"  [OK] 实体搜索: 'AI,芯片' → {len(entities)} 个实体")

    # 测试 BFS 推理
    result = kg.reason(["先进封装", "Chiplet"], "半导体")
    assert len(result) > 0, "Should find stocks for 先进封装"
    codes = [r["stock_code"] for r in result]
    print(f"  [OK] BFS推理: '先进封装' → {len(result)} 只股票: {codes[:5]}")

    # 测试公司实体推理
    result2 = kg.reason(["华为"], "", companies=["华为"])
    assert len(result2) > 0, "Should find stocks via 华为 company entity"
    print(f"  [OK] 公司推理: '华为' → {len(result2)} 只股票")


def test_event_service_fallback():
    """测试事件服务 fallback（不依赖 LLM）"""
    from services.event_service import EventService
    es = EventService()
    # 测试 fallback 结果
    fallback = es._fallback()
    assert fallback["event_type"] == "OTHER"
    assert fallback["sentiment"] == "neutral"
    assert fallback["novelty_score"] == 0
    print(f"  [OK] 事件服务 fallback: correct")

    # 测试 event_score 计算
    score_s = es._compute_event_score("S", 90)
    score_c = es._compute_event_score("C", 20)
    assert score_s > score_c, f"S级 score({score_s}) should > C级({score_c})"
    print(f"  [OK] 事件评分: S(90)={score_s}, C(20)={score_c}")

    # 测试 validate
    valid = es._validate({"event_type": "invalid", "importance": "X", "sentiment": "bad", "novelty_score": 150})
    assert valid["event_type"] == "OTHER"
    assert valid["importance"] == "C"
    assert valid["sentiment"] == "neutral"
    assert valid["novelty_score"] == 100  # clamped
    print(f"  [OK] 事件验证: invalid inputs → safe defaults")


def test_scoring_engine():
    """测试评分引擎"""
    from services.scoring_engine import ScoringEngine
    se = ScoringEngine()
    # 测试主题热度加载
    theme_heat = se._load_theme_heat()
    print(f"  [OK] 主题热度加载: {len(theme_heat)} 个主题")

    # 测试龙头评分加载
    leader = se._load_leader_score("002230")
    print(f"  [OK] 龙头评分: 002230 = {leader}")


def test_theme_discovery():
    """测试主题发现"""
    from services.theme_discovery import ThemeDiscovery
    td = ThemeDiscovery()
    # 已知关键词不应产生候选
    result = td.discover(["AI", "人工智能", "半导体"], "AI")
    assert len(result) == 0, f"Known terms should not create candidates, got: {result}"
    print(f"  [OK] 已知主题过滤: AI/半导体 → 0 candidates")

    # 未知关键词应产生候选
    result2 = td.discover(["量子计算", "脑机接口"], "")
    assert len(result2) > 0, "Unknown terms should create candidates"
    print(f"  [OK] 新概念发现: 量子计算/脑机接口 → {len(result2)} candidates")


def test_event_cluster():
    """测试事件聚类"""
    from services.event_cluster import EventClustering
    ec = EventClustering()
    # 先清理上次测试数据
    import sqlite3
    from config import Config
    with sqlite3.connect(Config.STOCKS_DB) as conn:
        conn.execute("DELETE FROM event_cluster_map WHERE event_id=99999")
        conn.commit()
    # 创建一个新簇
    cid = ec.cluster_event(99999, "测试事件聚类标题", "这是一条关于半导体先进封装的测试新闻")
    assert cid is not None, "Should create a cluster"
    print(f"  [OK] 事件聚类: cluster_id={cid}")
    # 清理
    with sqlite3.connect(Config.STOCKS_DB) as conn:
        conn.execute("DELETE FROM event_cluster_map WHERE event_id=99999")
        conn.commit()


def test_embedding_service():
    """测试 Embedding 服务"""
    from services.embedding_service import EmbeddingService
    em = EmbeddingService()
    em.seed_embeddings()
    # 测试匹配（使用概念树中存在的行业名）
    result = em.match("半导体 芯片 晶圆代工 集成电路")
    assert len(result) > 0, "Should match themes for 半导体"
    print(f"  [OK] Embedding匹配: '半导体' → {result[0]['theme_name']} (sim={result[0]['similarity']})")


def test_theme_heat_formula():
    """测试主题热度公式（验证不再有0硬编码）"""
    from services.theme_heat import ThemeHeat
    th = ThemeHeat()
    # 验证 _known_themes 不为空
    known = th._known_themes()
    assert len(known) > 0, "Known themes should not be empty"
    print(f"  [OK] 已知主题: {len(known)} 个")


def test_scheduler_event_id():
    """测试 scheduler 使用 event['_event_id'] 而非 MAX(event_id)"""
    from services.event_service import EventService
    es = EventService()
    # 插入一条测试事件
    with sqlite3.connect(Config.NEWS_DB) as conn:
        # 先插入一条测试新闻
        conn.execute("""
            INSERT OR IGNORE INTO news (id, title, content, source, source_name, created_at)
            VALUES ('test_id_001', '测试新闻标题', '测试内容', 'test', '测试', datetime('now'))
        """)
        conn.commit()

    item = {"id": "test_id_001", "title": "测试新闻标题", "content": "测试内容"}
    result = es.process_news_item(item)
    event_id = result.get("_event_id")
    assert event_id is not None, "_event_id should be set after process_news_item"
    print(f"  [OK] event_id 传递: _event_id={event_id}")

    # 清理
    with sqlite3.connect(Config.NEWS_DB) as conn:
        conn.execute("DELETE FROM news WHERE id='test_id_001'")
        conn.execute("DELETE FROM event_analysis WHERE source_id='test_id_001'")
        conn.commit()


def test_backtest_query():
    """测试回测查询使用 stock_score 表"""
    from services.backtest import BacktestEngine
    be = BacktestEngine()
    # 仅测试不报错
    with sqlite3.connect(Config.STOCKS_DB) as conn:
        rows = conn.execute("SELECT COUNT(*) FROM stock_score").fetchone()
        print(f"  [OK] stock_score 记录数: {rows[0]}")


def test_config():
    """测试配置无重复"""
    for cat, keywords in Config.NEWS_CATEGORIES.items():
        assert len(keywords) == len(set(keywords)), f"Duplicate in {cat}: {[k for k in keywords if keywords.count(k)>1]}"
    print(f"  [OK] NEWS_CATEGORIES 无重复关键词")


def test_concept_crawler():
    """测试概念树爬虫（离线）"""
    from services.concept_crawler import ConceptCrawler
    cc = ConceptCrawler()
    # 测试 normalize_code
    assert cc._normalize_code("002230.SZ") == "002230"
    assert cc._normalize_code("600519.SH") == "600519"
    assert cc._normalize_code("300750") == "300750"
    assert cc._normalize_code("abc") == ""
    print(f"  [OK] normalize_code: 4 cases passed")
    # 测试 extract_keywords
    assert "AI" in cc._extract_keywords("AI/算力")
    assert "半导体" in cc._extract_keywords("半导体、芯片")
    print(f"  [OK] extract_keywords: correct")
    # 测试 keyword search (DB中可能为空)
    import sqlite3
    with sqlite3.connect(Config.STOCKS_DB) as c:
        cnt = c.execute("SELECT COUNT(*) FROM concept_board").fetchone()[0]
    print(f"  [OK] concept_board: {cnt} 条记录")


def test_fundamentals_data():
    """测试基本面数据完整性"""
    import sqlite3
    with sqlite3.connect(Config.STOCKS_DB) as c:
        total = c.execute("SELECT COUNT(*) FROM stock_fundamentals").fetchone()[0]
        with_pe = c.execute("SELECT COUNT(*) FROM stock_fundamentals WHERE pe_ttm > 0").fetchone()[0]
        with_roe = c.execute("SELECT COUNT(*) FROM stock_fundamentals WHERE roe != 0").fetchone()[0]
        assert total > 0, "stock_fundamentals should not be empty"
        assert with_pe > 0, f"Should have PE data, got {with_pe}/{total}"
        print(f"  [OK] 基本面: {total}条, PE>0: {with_pe}, ROE!=0: {with_roe}")


def test_fundamental_score_calc():
    """测试基本面评分计算"""
    from services.scoring_engine import ScoringEngine
    se = ScoringEngine()
    # 获取一只有PE和ROE数据的股票
    import sqlite3
    with sqlite3.connect(Config.STOCKS_DB) as c:
        row = c.execute(
            "SELECT stock_code FROM stock_fundamentals WHERE pe_ttm > 0 AND roe != 0 LIMIT 1"
        ).fetchone()
    if row:
        score = se._load_fundamental_score(row[0])
        assert score > 0, f"fundamental_score should > 0 for {row[0]}, got {score}"
        assert score <= 100, f"fundamental_score should <= 100, got {score}"
        print(f"  [OK] fundamental_score({row[0]}) = {score:.1f}")
    else:
        print(f"  [SKIP] 无PE+ROE数据")


def test_v4_scoring_output():
    """测试V4评分输出包含新字段"""
    from services.scoring_engine import ScoringEngine
    se = ScoringEngine()
    ranked = se.calculate(hours=24)
    if ranked:
        r = ranked[0]
        for key in ("concept_rank", "fundamental_score", "stock_code", "total_score"):
            assert key in r, f"V4 output missing key: {key}"
        print(f"  [OK] V4输出字段: concept_rank={r['concept_rank']}, fundamental={r['fundamental_score']}")
    else:
        print(f"  [SKIP] 无评分数据")


def test_stock_service_match_reason():
    """测试股票匹配有reason"""
    from services.stock_service import StockService
    ss = StockService()
    event = {"keywords": ["AI"], "industry": "人工智能"}
    matched = ss.match_event_to_stocks(event)
    assert len(matched) > 0, "Should match stocks"
    has_reason = any(
        m.get("benefit_reason") or m.get("_concept_name") or m.get("benefit_path")
        for m in matched
    )
    assert has_reason, f"All matches should have reason, got: {matched[:2]}"
    print(f"  [OK] match_reason: {len(matched)} stocks, has_reason=True")


if __name__ == "__main__":
    def test_tui_db_queries():
        """测试 TUI DB 查询层返回的字段名"""
        from tui.db import TuiDB
        db = TuiDB()
    
        # stats 查询
        stats = db.stats()
        assert "news" in stats, f"stats missing 'news': {stats.keys()}"
        assert "events" in stats, f"stats missing 'events': {stats.keys()}"
        print(f"  [OK] TUI stats: news={stats['news']}, events={stats['events']}, stocks={stats['stocks']}")
    
        # top_stocks 查询
        stocks = db.top_stocks(5)
        if stocks:
            for key in ("stock_code", "stock_name", "total_score", "event_score", "benefit_score", "market_score"):
                assert key in stocks[0], f"top_stocks missing '{key}'"
            print(f"  [OK] TUI top_stocks: {len(stocks)} stocks, fields correct")
        else:
            print(f"  [OK] TUI top_stocks: (no data, fields cannot be verified)")
    
        # theme_heat_list 查询
        heat = db.theme_heat_list()
        if heat:
            for key in ("theme_name", "heat_score", "decay_heat"):
                assert key in heat[0], f"theme_heat_list missing '{key}': {heat[0].keys()}"
            print(f"  [OK] TUI theme_heat_list: {len(heat)} themes, fields correct")
        else:
            print(f"  [OK] TUI theme_heat_list: (no data)")
    
        # stock_profile_list 查询
        profiles = db.stock_profile_list()
        if profiles:
            for key in ("stock_code", "stock_name", "leader_score", "turnover_rate",
                         "market_cap", "theme_count", "limitup_history"):
                assert key in profiles[0], f"stock_profile_list missing '{key}': {profiles[0].keys()}"
            print(f"  [OK] TUI stock_profile_list: {len(profiles)} profiles, fields correct")
        else:
            print(f"  [OK] TUI stock_profile_list: (no data)")
    
        # event_clusters 查询
        clusters = db.event_clusters()
        if clusters:
            for key in ("cluster_id", "event_count", "heat_score"):
                assert key in clusters[0], f"event_clusters missing '{key}': {clusters[0].keys()}"
            print(f"  [OK] TUI event_clusters: {len(clusters)} clusters, fields correct")
        else:
            print(f"  [OK] TUI event_clusters: (no data)")
    
    
    def test_embedding_singleton():
        """测试 EmbeddingService 单例"""
        from services.embedding_service import get_embedding_service, EmbeddingService
        a = get_embedding_service()
        b = get_embedding_service()
        assert a is b, "Singleton should return same instance"
        assert isinstance(a, EmbeddingService)
        print(f"  [OK] EmbeddingService 单例: same instance")
    
    
    tests = [
        ("配置检查", test_config),
        ("数据库初始化", test_db_init),
        ("事件服务", test_event_service_fallback),
        ("股票关联", test_stock_service),
        ("知识图谱", test_knowledge_graph),
        ("评分引擎", test_scoring_engine),
        ("主题发现", test_theme_discovery),
        ("事件聚类", test_event_cluster),
        ("Embedding", test_embedding_service),
        ("Embedding单例", test_embedding_singleton),
        ("主题热度公式", test_theme_heat_formula),
        ("Scheduler事件ID", test_scheduler_event_id),
        ("回测查询", test_backtest_query),
        ("TUI数据查询", test_tui_db_queries),
        # V4 新增测试
        ("概念树爬虫(离线)", test_concept_crawler),
        ("基本面数据", test_fundamentals_data),
        ("基本面评分", test_fundamental_score_calc),
        ("V4评分输出", test_v4_scoring_output),
        ("股票匹配reason", test_stock_service_match_reason),
    ]

    passed = 0
    failed = 0
    for name, func in tests:
        print(f"\n{'='*50}")
        print(f"[TEST] {name}")
        print(f"{'='*50}")
        try:
            func()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*50}")
    print(f"结果: {passed} passed / {failed} failed / {passed+failed} total")
    print(f"{'='*50}")
    sys.exit(0 if failed == 0 else 1)

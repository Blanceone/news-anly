# A股情报系统 — Agent Guide

## Secrets / API Keys

All tokens and API keys are stored in `C:\Users\13979\Desktop\notes\apis.txt`. Always read from that file when any credential is needed. Never hardcode keys in code or commit them.

## GitHub Commit Rule

每次提交到 GitHub 前，必须检查是否需要更新 `README.md`：
- 新增功能/模块/配置文件 → 更新 README 项目结构或功能描述
- 数据源/依赖/配置变更 → 更新 README 对应章节
- 若本次变更不涉及用户可见变化，则无需更新

## Commands

```bash
pip install -r requirements.txt
cp .env.example .env        # then edit with keys
python main.py run           # 单次增量采集+分析+推送
python main.py run --loop    # 持续循环采集（默认5秒间隔）
python main.py run --loop -i 30  # 自定义间隔（秒）
python main.py init          # check config
python main.py tui           # TUI终端
```

## Architecture

Single Python app, orchestrated by `scheduler.py`. New business services in `services/`.

```
collectors/ (fetch) → services/event_service.py (AI事件抽取) → services/stock_service.py (股票关联+受益链分层)
                    ↘ SQLite (news.db + event_analysis + stock_mapping)
                    ↗ services/knowledge_graph.py (知识图谱推理+BFS)
                    ↗ services/scoring_engine.py (评分V3→推荐榜HOT/THEME/LATENT)
                    ↗ services/theme_heat.py (主题热度+衰减+涨停)
                    ↗ services/event_cluster.py (事件聚类+生命周期)
                    ↗ services/stock_profile.py (龙头评分)
```

Entrypoint: `main.py` parses `{run, init, tui}`.

## Project Structure

```
news-anly/
├── main.py                 # CLI entrypoint (run / init / tui)
├── tui/                    # Textual TUI 终端
│   ├── app.py              # Main app: top-bar nav (1-6), clock, bindings
│   ├── db.py               # DB query layer for TUI screens
│   ├── screens/
│   │   ├── dashboard.py    # Dashboard: 统计栏 + 新闻流 + 推荐榜 + 题材
│   │   ├── theme_view.py   # Theme View: 三栏 (行业板块/概念主题/成分股)
│   │   ├── stock_view.py   # Stock View: 评分排序 → 事件/主题详情
│   │   ├── event_view.py   # Event View: 事件列表 → 影响股票 + 来源新闻
│   │   ├── discovery_view.py # Discovery: 新概念候选 + 晋升official
│   │   └── cluster_view.py # Cluster: 事件聚类视图
│   └── widgets/            # (reserved for shared widgets)
├── config.py               # All config: sources, categories, API keys, retention
├── collectors/             # Data source handlers
│   ├── __init__.py         # NewsCollector: pipeline + DB (freshness, analyzed flag)
│   ├── cls.py              # 财联社 - sign-based JSON API, accepts since param
│   └── cninfo.py           # 巨潮资讯 - POST form announcements, accepts since param
├── services/               # 业务服务层 (15 modules)
│   ├── __init__.py
│   ├── llm_client.py       # 统一 LLM 调用客户端
│   ├── event_service.py    # AI事件识别（结构化JSON输出）
│   ├── stock_service.py    # 股票关联映射（关键词→DIRECT, Embedding→INDIRECT, KG→SENTIMENT）
│   ├── knowledge_graph.py  # 知识图谱（47实体+82关系+BFS推理）
│   ├── scoring_engine.py   # 评分系统V3（7维公式→HOT/THEME/LATENT策略）
│   ├── market_verifier.py  # 市场验证引擎（Tushare行情→MarketScore）
│   ├── theme_heat.py       # 主题热度（新闻40%+板块20%+涨停15%+衰减半衰期3天）
│   ├── theme_discovery.py  # 新概念自动发现（candidate→observing→official三级）
│   ├── embedding_service.py# TF-IDF语义匹配（char_wb ngram, cosine阈值0.3）
│   ├── event_cluster.py    # 事件聚类+生命周期（BIRTH→GROWING→PEAK→DECLINING→DEAD）
│   ├── stock_profile.py    # 股票画像+龙头评分（流动性/活跃度/题材数/涨停历史）
│   ├── limitup_stats.py    # 涨停热度（涨停/连板/炸板按主题聚合）
│   └── backtest.py         # 回测系统（持仓1/3/5/10/20天, 胜率/夏普/回撤）
├── core/                   # Business logic
│   ├── analyzer.py         # LLM analysis + mark-as-analyzed
│   ├── db_init.py          # 双数据库初始化 (news.db + stocks.db 18张表)
│   ├── scheduler.py        # Single run() flow: fetch → analyze → push
│   └── feishu_pusher.py    # Feishu card message push
├── docs/                   # 架构文档
│   └── 架构说明.md
├── PLAN_V3.md              # V3 开发计划
└── .github/workflows/      # (仅存根)
```

## Config

All config lives in `config.py` + `.env` loaded via `python-dotenv`.

- **AI providers** (probed in order): Gemini > DeepSeek > OpenAI-compat. Fallback = keyword classification only.
- **DATA_RETENTION_HOURS** (default 72): old data auto-deleted on each run.
- **NEWS_SOURCES**: dict in `config.py`. Each entry has source-specific URL/params.
- **NEWS_CATEGORIES**: substring keyword matching dict.
- **TUSHARE_TOKEN** in `.env`: Sectors + daily quotes + limitup data
- `.env` is gitignored.

## Data Sources — Known State

| Source | Type | Status | Detail |
|--------|------|--------|--------|
| cls (财联社) | JSON API | ✅ incremental | Sign: SHA1→MD5 of sorted params. `last_time` set to `since` timestamp. Client-side ctime filter. |
| cninfo (巨潮资讯) | POST form | ✅ incremental + pagination | Sorted by `annDate desc`, client-side time filter with multi-page pull. |

Adding a new data source requires:
1. Entry in `config.py` `NEWS_SOURCES` dict
2. New source file with `collect(config, since=None) -> list[dict]`
3. Register module in `collectors/__init__.py` `_HANDLERS` dict

## SQLite Schema

Auto-created `news.db` with tables:
- `news(id TEXT PK, title, content, summary, source, source_name, url, category, sentiment, impact, related_stocks, ai_analysis, freshness TEXT DEFAULT 'medium', analyzed INTEGER DEFAULT 0, created_at, updated_at)`
- `reports(id INTEGER PK, type, title, content, created_at)` (保留, 未使用)
- `event_analysis(id INTEGER PK, news_id TEXT FK, title, content, event_type, event_keywords, industry_tags, sentiment, impact_level, involved_stocks, summary, analysis_time)`

`stocks.db` 包含以下 18 张表:
- `stock_basic` — 全市场股票代码/名称/行业
- `theme_stock_mapping` — 主题→受益股映射
- `event_stock_mapping` — 事件→股票关联 (含 benefit_type/benefit_path)
- `market_confirmation` — 板块行情验证（市场验证引擎）
- `stock_score` — 单因子评分存储
- `recommendation_result` — 推荐结果 (strategy_type区分HOT/THEME/LATENT)
- `sector_cache` — 板块缓存
- `kg_entity` / `kg_relation` / `kg_direct_benefit` — 知识图谱（47实体/82关系/42直连受益）
- `theme_candidate` — 新概念候选区（candidate→observing→official）
- `theme_embedding` — TF-IDF embedding 缓存
- `event_cluster` / `event_cluster_map` — 事件聚类（含生命周期字段）
- `theme_heat` — 主题热度（含衰减后heat/最后活跃时间）
- `stock_profile` — 股票画像（换手率/市值/题材数/涨停历史/龙头评分）
- `theme_limitup_stats` — 涨停热度（涨停数/连板数/炸板数/行业/概念）
- `backtest_result` / `backtest_trades` — 回测结果

## Freshness
- **high**: `created_at` within 1 hour
- **medium**: 1–24 hours
- **low**: >24 hours
- Updated automatically on every `collect_since()` call.

## Analysis Flag
- `analyzed = 0`: not yet analyzed by AI
- `analyzed = 1`: AI analysis written to DB (category, sentiment, impact, etc.)
- On each `run()`, fetches unanalyzed items, runs AI, marks as analyzed.
- Prevents re-analysis across restarts.

## TUI Terminal

启动: `python main.py tui` 或 `python -m tui.app`

| 按键 | 功能 |
|------|------|
| 1 | Dashboard（新闻流+推荐榜+题材） |
| 2 | Theme View（三栏：行业板块/概念主题/成分股） |
| 3 | Stock View（评分排序→事件详情） |
| 4 | Event View（事件列表→影响股票） |
| 5 | Discovery（新概念候选列表） |
| 6 | Clusters（事件聚类视图） |
| r | 手动刷新当前页面 |
| q | 退出 |

- Dashboard 10秒自动刷新，其余页面30秒自动刷新

## 评分公式 (V3)

```
Total = EventScore×15% + BenefitScore(分层)×20% + MarketScore×15%
      + ThemeHeat(衰减)×15% + ClusterHeat(生命周期)×10%
      + LeaderScore×15% + LifecycleScore×10%
```

### 受益链分层

| 类型 | 权重 | 来源 |
|------|------|------|
| DIRECT | 1.0 | 关键词匹配 / theme_stock level=1 / KG 1跳 |
| INDIRECT | 0.8 | Embedding匹配 / KG 2-3跳 |
| SENTIMENT | 0.5 | KG 3跳+ / 题材跟风 |

### 生命周期

| 阶段 | 系数 | 条件 |
|------|------|------|
| BIRTH | 0.8 | 首次出现 < 24h |
| GROWING | 1.0 | event_count ≥ 3 |
| PEAK | 0.7 | event_count ≥ 10 |
| DECLINING | 0.3 | 超24h无新增 |
| DEAD | 0.0 | 超72h无新增 |

## Noteworthy

- Feishu card messages are interactive JSON, sent via webhook POST. No Feishu SDK.
- Data older than 72 hours is auto-deleted on each run (`DATA_RETENTION_HOURS`).
- MarketVerifier only runs during trading hours (weekdays 9:25-15:00), otherwise returns score 0.
- Scoring formula V3: 7维, 多策略输出 (HOT/THEME/LATENT).
- cls `collect()` passes `since` as `last_time` API param — only gets items after that time.
- cninfo `collect()` paginates up to 5 pages, stops when items are older than `since`.
- TUSHARE_TOKEN: 配置在 `.env` 中，从 https://tushare.pro 获取
- Knowledge Graph: 47 entities, 82 relations, 42 direct benefits, BFS non-weighted + COMPETITOR skipped.
- Database separation: news.db (lightweight) + stocks.db (18 tables for analysis results).
- `event_stock_mapping` receives results from both StockService (keyword/embedding) and KG (BFS).

# A股概念发现与验证系统 — Agent Guide

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
python main.py run           # 单次增量采集+分析+概念发现
python main.py run --loop    # 持续循环采集（默认5秒间隔）
python main.py run --loop -i 30  # 自定义间隔（秒）
python main.py init          # check config
python main.py tui           # TUI终端
python -m pytest tests/      # 运行测试 (29项)
```

## Architecture

Single Python app, orchestrated by `scheduler.py`. 核心流程: 新闻采集 → AI事件抽取(Spec 3.1) → 概念归一化(Spec 3.2) → 7信号验证 → 风控决策。

```
collectors/ (fetch) → services/event_service.py (Spec 3.1事件抽取 + Spec 3.2概念归一化)
                    ↘ SQLite (news.db: news + reports + event_analysis)
                    ↘ SQLite (concept.db: 12表+1日志表)
                    ↗ services/concept_discovery.py (概念候选+升级检查)
                    ↗ services/capital_detector.py (AKShare: 涨停/龙虎榜/北向/异动)
                    ↗ services/market_monitor.py (AKShare: 大盘量能/板块)
                    ↗ services/concept_validator.py (7信号验证)
                    ↗ services/stock_validator.py (个股3步验证: relevance/announce/report)
                    ↗ services/risk_control.py (风控: chasing_high/no_event_support/low_volume)
```

Entrypoint: `main.py` parses `{run, init, tui}`.

## Project Structure

```
news-anly/
├── main.py                 # CLI entrypoint (run / init / tui)
├── tui/                    # Textual TUI 终端 (5页签)
│   ├── app.py              # Main app: top-bar nav (1-5), bindings
│   ├── db.py               # DB query layer for TUI screens
│   ├── screens/
│   │   ├── dashboard.py    # 1: main_concept列表 + 连板龙头 + 风控预警
│   │   ├── concepts_view.py# 2: 概念候选池 (standard_name/status/mention_count)
│   │   ├── validation_view.py # 3: 7信号验证 + 概念评分 + 个股3步验证
│   │   ├── capital_view.py # 4: 北向TOP10 + 涨停 + 龙虎榜(buyer_type)
│   │   └── sources_view.py # 5: 事件时间线(raw_concepts) + 风控(risk_type)
│   └── widgets/
├── config.py               # All config: sources, API keys, retention
├── collectors/             # Data source handlers
│   ├── __init__.py         # NewsCollector: pipeline + DB (freshness, is_processed)
│   ├── cls.py              # 财联社 - sign-based JSON API, accepts since param
│   └── cninfo.py           # 巨潮资讯 - POST form announcement, accepts since param
├── services/               # 业务服务层 (8 modules)
│   ├── __init__.py
│   ├── event_service.py    # Spec 3.1事件抽取 + Spec 3.2概念归一化 (双Prompt)
│   ├── concept_discovery.py# 概念候选池 + 升级检查 (mention_count>=3 → observing)
│   ├── concept_validator.py# 7信号验证（>=5主线, 4存疑, <=3一日游）
│   ├── stock_validator.py  # 个股3步验证（relevance/announce_check/report_check）
│   ├── capital_detector.py # AKShare: 涨停/龙虎榜/北向资金/异动
│   ├── market_monitor.py   # AKShare: 大盘指数/量能
│   ├── source_monitor.py   # 信息源监控（Tier 1-6）
│   └── risk_control.py     # 风控引擎（chasing_high/no_event_support/low_volume）
├── core/                   # 核心模块
│   ├── llm_client.py       # 统一 LLM 调用客户端
│   ├── db_init.py          # 双数据库初始化 (news.db 3表 + concept.db 12表+1日志)
│   └── scheduler.py        # SOP三阶段调度: 盘前/盘中/盘后(细化子阶段)
├── tests/                  # 测试 (29项)
│   ├── test_event_service.py       # 5项: 事件抽取/入库/词典归一化/候选/fallback
│   ├── test_concept_validator.py   # 12项: 7信号/判定/入库/概念升级
│   ├── test_capital_detector.py    # 6项: 涨停/龙虎榜/北向/异动
│   └── test_risk_control.py        # 6项: 事件支撑/追高/入库/安全
├── prd/                    # 产品需求文档
├── docs/                   # 架构文档
├── .env                    # 环境变量 (gitignored)
└── requirements.txt
```

## Config

All config lives in `config.py` + `.env` loaded via `python-dotenv`.

- **AI providers** (probed in order): Gemini > DeepSeek > OpenAI-compat.
- **DATA_RETENTION_HOURS** (default 72): old data auto-deleted on each run.
- **NEWS_SOURCES**: dict in `config.py`. Each entry has source-specific URL/params.
- **AKShare**: 涨停/龙虎榜/北向/板块数据 (无需Token，开源)
- `.env` is gitignored.

## Data Sources — Known State

| Source | Type | Status | Detail |
|--------|------|--------|--------|
| cls (财联社) | JSON API | ✅ incremental | Sign: SHA1→MD5 of sorted params. |
| cninfo (巨潮资讯) | POST form | ✅ incremental + pagination | Sorted by `annDate desc`. |

## SQLite Schema

### news.db (3表)
- `news(id TEXT PK, source, source_name, url, title, content, publish_time, is_processed INTEGER DEFAULT 0, category, sentiment, impact, related_stocks, ai_analysis, freshness TEXT DEFAULT 'medium', analyzed INTEGER DEFAULT 0, created_at, updated_at)`
- `reports(id INTEGER PK, type, title, content, created_at)` (保留)
- `event_analysis(id INTEGER PK, news_id TEXT, event_type, entities TEXT, summary, sentiment, raw_concepts TEXT, created_at)`

### concept.db (12表+1日志, 4域)

**域A: 概念基础 (2表)**
- `concept_dictionary(id INTEGER PK, standard_name TEXT UNIQUE, aliases TEXT, category, status DEFAULT 'active')` — 标准概念词典
- `concept_candidate(id INTEGER PK, standard_name TEXT UNIQUE, status DEFAULT 'candidate', created_at, mention_count INTEGER DEFAULT 0, last_mention_date DATE)` — 概念候选池

**域B: 关联关系 (2表)**
- `concept_stock(concept_id INTEGER, stock_code TEXT, role TEXT, is_target INTEGER DEFAULT 0)` — PK(concept_id, stock_code)
- `concept_event(concept_id INTEGER, event_id INTEGER, trade_date DATE)` — PK(concept_id, event_id)

**域C: 市场与资金 (4表)**
- `limitup_stats(trade_date DATE, concept_id INTEGER, limitup_count INTEGER, max_consecutive_boards INTEGER)` — PK(trade_date, concept_id)
- `capital_anomaly(stock_code TEXT, trade_date DATE, anomaly_type TEXT, detail TEXT)` — PK(stock_code, trade_date, anomaly_type)
- `dragon_tiger(id INTEGER PK, trade_date DATE, stock_code TEXT, buyer_name TEXT, net_buy REAL, buyer_type TEXT)` — buyer_type: institution/hot_money/retail
- `northbound_flow(trade_date DATE, stock_code TEXT, net_buy REAL)` — PK(trade_date, stock_code) 按个股

**域D: 验证与决策 (4表)**
- `concept_validation(concept_id INTEGER, trade_date DATE, signal_no INTEGER, is_met INTEGER, evidence TEXT)` — PK(concept_id, trade_date, signal_no)
- `stock_validation(stock_code TEXT, concept_id INTEGER, trade_date DATE, relevance TEXT, announce_check TEXT, report_check TEXT)` — PK(stock_code, concept_id, trade_date) 单行设计
- `risk_check(id INTEGER PK, concept_id INTEGER, trade_date DATE, risk_type TEXT, detail TEXT)` — risk_type: chasing_high/no_event_support/low_volume
- `concept_score(concept_id INTEGER, trade_date DATE, signal_count INTEGER, verdict TEXT)` — PK(concept_id, trade_date) verdict: main_concept/uncertain/one_day_wonder

**日志表**
- `sop_log(id INTEGER PK, phase TEXT, task_name TEXT, status TEXT, detail TEXT, started_at TIMESTAMP, finished_at TIMESTAMP)`

## SOP 三阶段调度

| 阶段 | 时间 | 动作 |
|------|------|------|
| Pre-market | 7:00-9:15 | 采集→事件抽取(Spec 3.1)→概念归一化(Spec 3.2)→题材预判 |
| Intraday | 9:15-15:00 | 增量采集→资金异动(AKShare)→涨停监控→触发验证→风控 (10min循环) |
| Post-market | 15:00-22:00 | 15:30涨停复盘→17:00龙虎榜→18:00北向→19:00全量验证→20:00评分→风控终检 |

## 7信号验证清单

| # | 信号 | 达标条件 |
|---|------|----------|
| 1 | 源头事件可查 | **必须满足** |
| 2 | 3日净流入递增 | 连续3日有资金异动 |
| 3 | 涨停>=5只 | 概念涨停数>=5 |
| 4 | 竞价抢筹>=3000万 | 龙头股竞价验证 |
| 5 | 上下游扩散 | >=2种角色, >=5只股票 |
| 6 | 媒体热度拐点 | >=5次提及 或 >=3天连续 |
| 7 | 研报覆盖 | 龙虎榜/研报>=2条 |

- **>=5信号 → main_concept (participate)**
- **4信号 → uncertain (observe)**
- **<=3信号 → one_day_wonder (avoid)**

## 概念生命周期

| 升级路径 | 条件 |
|----------|------|
| candidate → observing | mention_count >= 3 且 last_mention_date 在2天内 |

概念候选池通过 `event_service.py` 归一化流程自动激活，mention_count 每次提及+1，last_mention_date 更新为当天。

## TUI Terminal

启动: `python main.py tui`

| 按键 | 页签 | 内容 |
|------|------|------|
| 1 | Dashboard | main_concept列表 + 连板龙头 + 风控预警表 |
| 2 | Concepts | 概念候选池 (standard_name/status/mention_count/is_target) |
| 3 | Validation | 7信号验证详情 + concept_score(verdict) + 个股3步(relevance/announce/report) |
| 4 | Capital | 北向TOP10 + 涨停(max_consecutive_boards) + 龙虎榜(buyer_type) |
| 5 | Sources | 事件时间线(raw_concepts) + 风控(risk_type/detail) |
| r | 刷新 | 手动刷新当前页面 |
| q | 退出 | |

## Freshness
- **high**: `created_at` within 1 hour
- **medium**: 1–24 hours
- **low**: >24 hours

## Analysis Flag
- `analyzed = 0`: not yet analyzed by AI
- `analyzed = 1`: AI analysis written to DB
- Prevents re-analysis across restarts.

## Noteworthy

- Data older than 72 hours is auto-deleted on each run.
- news.db (新闻+事件) 与 concept.db (概念验证系统) 分离。
- MarketMonitor only meaningful during trading hours (weekdays 9:25-15:00).
- CapitalDetector/MarketMonitor 使用 AKShare (开源, 无需Token): stock_zt_pool_em, stock_lhb_detail_em, stock_hsgt_north_net_flow_in_em, stock_zh_index_daily.
- EventService 双Prompt设计: Spec 3.1事件抽取 + Spec 3.2概念归一化，均通过 LLM 完成。
- concept_dictionary 表是概念归一化的核心，LLM将raw_keyword映射到standard_name。
- stock_validation 单行设计: (stock_code, concept_id, trade_date) → relevance/announce_check/report_check。
- RiskControl: risk_type 枚举: chasing_high / no_event_support / low_volume。

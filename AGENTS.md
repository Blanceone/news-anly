# A股概念发现系统 — Agent Guide

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
python -m pytest tests/      # 运行测试
```

## Architecture

Single Python app, orchestrated by `scheduler.py`. 核心流程: 新闻采集 → AI事件抽取 → 概念发现 → 7信号验证 → 风控决策。

```
collectors/ (fetch) → services/event_service.py (AI事件抽取) → services/concept_discovery.py (概念发现+升级)
                    ↘ SQLite (news.db: news + event_analysis)
                    ↗ services/capital_detector.py (涨停/龙虎榜/北向/资金异动)
                    ↗ services/market_monitor.py (大盘量能/板块/情绪)
                    ↗ services/concept_validator.py (7信号验证)
                    ↗ services/stock_validator.py (个股3步验证)
                    ↗ services/risk_control.py (风控红线)
                    ↗ services/source_monitor.py (信息源Tier 1-6)
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
│   │   ├── dashboard.py    # 1: SOP阶段 + 概念验证摘要 + 风控 + 量能
│   │   ├── concepts_view.py# 2: 概念候选池 (状态/生命周期/信号/verdict)
│   │   ├── validation_view.py # 3: 7信号验证 + 概念评分 + 个股3步验证
│   │   ├── capital_view.py # 4: 资金异动 + 涨停 + 龙虎榜 + 北向
│   │   └── sources_view.py # 5: 信息源状态 + 风控总览 + 事件
│   └── widgets/
├── config.py               # All config: sources, API keys, retention
├── collectors/             # Data source handlers
│   ├── __init__.py         # NewsCollector: pipeline + DB (freshness, analyzed flag)
│   ├── cls.py              # 财联社 - sign-based JSON API, accepts since param
│   └── cninfo.py           # 巨潮资讯 - POST form announcement, accepts since param
├── services/               # 业务服务层 (8 modules)
│   ├── __init__.py
│   ├── event_service.py    # AI事件识别（结构化JSON输出, concept_keywords提取）
│   ├── concept_discovery.py# 概念发现引擎（candidate→observing→validated）
│   ├── concept_validator.py# 7信号验证（>=5主线, 4存疑, <=3一日游）
│   ├── stock_validator.py  # 个股3步验证（业务关联/公告/研报）
│   ├── capital_detector.py # 资金异动（涨停/龙虎榜/北向/竞价）
│   ├── market_monitor.py   # 市场监控（大盘量能/板块/情绪）
│   ├── source_monitor.py   # 信息源监控（Tier 1-6）
│   └── risk_control.py     # 风控引擎（追高/事件支撑/量能/止损）
├── core/                   # 核心模块
│   ├── llm_client.py       # 统一 LLM 调用客户端
│   ├── db_init.py          # 双数据库初始化 (news.db 3表 + concept.db 12表)
│   └── scheduler.py        # SOP三阶段调度: 盘前/盘中/盘后
├── tests/                  # 测试
│   ├── test_concept_discovery.py
│   ├── test_concept_validator.py
│   ├── test_capital_detector.py
│   └── test_risk_control.py
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
- **TUSHARE_TOKEN** in `.env`: 涨停/龙虎榜/北向/板块数据
- `.env` is gitignored.

## Data Sources — Known State

| Source | Type | Status | Detail |
|--------|------|--------|--------|
| cls (财联社) | JSON API | ✅ incremental | Sign: SHA1→MD5 of sorted params. |
| cninfo (巨潮资讯) | POST form | ✅ incremental + pagination | Sorted by `annDate desc`. |

## SQLite Schema

### news.db (3表)
- `news(id TEXT PK, title, content, summary, source, source_name, url, category, sentiment, impact, related_stocks, ai_analysis, freshness TEXT DEFAULT 'medium', analyzed INTEGER DEFAULT 0, created_at, updated_at)`
- `reports(id INTEGER PK, type, title, content, created_at)` (保留)
- `event_analysis(event_id INTEGER PK, source_type, source_id, event_type, event_subtype, industry, sub_industry, sentiment, importance, novelty_score, event_score, entities_json, amount, amount_unit, keywords_json, ai_summary, reason, raw_response, created_at)`

### concept.db (12表, 4域)

**域A: 概念发现 (3表)**
- `concept_candidate` — 概念候选池 (status: candidate/observing/validated/rejected, lifecycle: BIRTH/GROWING/PEAK/DECLINING/DEAD)
- `concept_stock` — 概念→股票映射 (role: leader/member/upstream/downstream)
- `concept_event` — 概念→事件关联

**域B: 7信号验证 (1表)**
- `concept_validation` — 7信号 (signal_no 1-7, is_met, evidence, score)

**域C: 资金与市场 (4表)**
- `capital_anomaly` — 资金异动 (volume_breakout/auction_rush/dragon_tiger/northbound)
- `limitup_stats` — 涨停统计 (按概念聚合)
- `dragon_tiger` — 龙虎榜
- `northbound_flow` — 北向资金日度

**域D: 风控与决策 (4表)**
- `stock_validation` — 个股3步验证 (business/announcement/research)
- `risk_check` — 风控检查 (追高/事件支撑/量能/止损)
- `concept_score` — 综合评分 (verdict: main_concept/uncertain/one_day_wonder)
- `sop_log` — SOP执行日志

## SOP 三阶段调度

| 阶段 | 时间 | 动作 |
|------|------|------|
| Pre-market | 7:00-9:15 | 采集→事件抽取→概念发现→输出题材预判 |
| Intraday | 9:15-15:00 | 增量采集→资金异动→涨停监控→触发验证→风控 |
| Post-market | 15:00-22:00 | 涨停复盘→龙虎榜→北向→全量验证→评分→风控终检 |

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

| 阶段 | 系数 | 条件 |
|------|------|------|
| BIRTH | - | 首次发现 |
| GROWING | - | mention>=3, days>=2 → observing |
| PEAK | - | mention>=5 → validated |
| DECLINING | - | 72h无新增 |
| DEAD | - | 7天无新增 |

## TUI Terminal

启动: `python main.py tui`

| 按键 | 页签 | 内容 |
|------|------|------|
| 1 | Dashboard | SOP阶段 + 概念验证摘要 + 风控状态 + 大盘量能 |
| 2 | Concepts | 概念候选池 (状态/生命周期/信号数/verdict) |
| 3 | Validation | 7信号验证详情 + 概念评分 + 个股3步验证 |
| 4 | Capital | 资金异动 + 涨停统计 + 龙虎榜 + 北向 |
| 5 | Sources | 信息源采集状态 + 风控总览 + 事件时间线 |
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
- concept.db is separate from news.db.
- MarketMonitor only meaningful during trading hours (weekdays 9:25-15:00).
- CapitalDetector requires TUSHARE_TOKEN for real data.
- SourceMonitor: Tier 1-4 are framework placeholders, Tier 2 (cninfo) + Tier 5 (cls) are active.
- RiskControl: chase_high check uses concept lifecycle, stop_loss is always a reminder.

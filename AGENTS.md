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
collectors/ (fetch) → services/event_service.py (AI事件抽取) → services/stock_service.py (股票关联) → core/feishu_pusher.py (push)
                    ↘ SQLite (news.db + event_analysis + stock_mapping)      ↗ services/knowledge_graph.py (知识图谱推理)
                                                                             ↗ services/scoring_engine.py (评分→推荐榜)
```

Entrypoint: `main.py` parses `{run, init}`.

## Project Structure

```
news-anly/
├── main.py                 # CLI entrypoint (run / init)
├── tui/                    # Textual TUI 终端
│   ├── app.py              # Main app: top-bar nav (1-4), clock, bindings
│   ├── db.py               # DB query layer for TUI screens
│   ├── screens/
│   │   ├── dashboard.py    # Dashboard: news feed + top stocks + hot themes
│   │   ├── theme_view.py   # Theme View: theme list → stock detail
│   │   ├── stock_view.py   # Stock View: score listing → detail (events/themes)
│   │   └── event_view.py   # Event View: event list → affected stocks
│   └── widgets/            # (reserved for shared widgets)
├── config.py               # All config: sources, categories, API keys, retention
├── collectors/             # Data source handlers
│   ├── __init__.py         # NewsCollector: pipeline + DB (freshness, analyzed flag)
│   ├── cls.py              # 财联社 - sign-based JSON API, accepts since param
│   └── cninfo.py           # 巨潮资讯 - POST form announcements, accepts since param
├── services/               # 业务服务层
│   ├── __init__.py
│   ├── llm_client.py       # 统一 LLM 调用客户端
│   ├── event_service.py    # AI事件识别（结构化JSON输出）
│   ├── stock_service.py    # 股票关联映射（主题→受益股）
│   ├── knowledge_graph.py  # 知识图谱（实体+关系+BFS推理）
│   ├── scoring_engine.py   # 评分系统（事件+受益→综合评分）
│   └── market_verifier.py  # 市场验证引擎（行情数据→MarketScore）
├── core/                   # Business logic
│   ├── analyzer.py         # LLM analysis + mark-as-analyzed
│   ├── scheduler.py        # Single run() flow: fetch → analyze → push
│   └── feishu_pusher.py    # Feishu card message push
└── .github/workflows/      # (仅存根)
```

## Config

All config lives in `config.py` + `.env` loaded via `python-dotenv`.

- **AI providers** (probed in order): Gemini > DeepSeek > OpenAI-compat. Fallback = keyword classification only.
- **DATA_RETENTION_HOURS** (default 72): old data auto-deleted on each run.
- **NEWS_SOURCES**: dict in `config.py`. Each entry has source-specific URL/params.
- **NEWS_CATEGORIES**: substring keyword matching dict.
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
- `market_confirmation(id PK, event_id, board_name, sector_change, volume_amount, up_count, down_count, confirmation_score, calculated_at)`

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
| 2 | Theme View（主题列表→关联股票） |
| 3 | Stock View（评分排序→事件详情） |
| 4 | Event View（事件列表→影响股票） |
| r | 手动刷新当前页面 |
| q | 退出 |

- Dashboard 10秒自动刷新，其余页面30秒自动刷新

## Noteworthy

- Feishu card messages are interactive JSON, sent via webhook POST. No Feishu SDK.
- Data older than 72 hours is auto-deleted on each run (`DATA_RETENTION_HOURS`).
- MarketVerifier only runs during trading hours (weekdays 9:25-15:00), otherwise returns score 0.
- Scoring formula: `Total = Event×30% + Benefit×40% + Market×30%`.
- cls `collect()` passes `since` as `last_time` API param — only gets items after that time.
- cninfo `collect()` paginates up to 5 pages, stops when items are older than `since`.
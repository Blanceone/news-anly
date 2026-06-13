# A股情报系统 — Agent Guide

## Secrets / API Keys

All tokens and API keys are stored in `C:\Users\13979\Desktop\notes\apis.txt`. Always read from that file when any credential is needed. Never hardcode keys in code or commit them.

## Commands

```bash
pip install -r requirements.txt
cp .env.example .env        # then edit with keys
python main.py run           # 单次增量采集+分析+推送
python main.py run --loop    # 持续循环采集（默认60秒间隔）
python main.py run --loop -i 30  # 每30秒轮询
python main.py init          # check config
```

## Architecture

Single Python app, 3 loosely-coupled modules orchestrated by `scheduler.py`.

```
config.py → collectors/ (fetch) → core/analyzer.py (analyze) → core/feishu_pusher.py (push)
                          ↘ SQLite (news.db) stores all articles
```

Entrypoint: `main.py` parses `{run, init}`.

## Project Structure

```
news-anly/
├── main.py                 # CLI entrypoint (run / init)
├── config.py               # All config: sources, categories, API keys, retention
├── collectors/             # Data source handlers
│   ├── __init__.py         # NewsCollector: pipeline + DB (freshness, analyzed flag)
│   ├── cls.py              # 财联社 - sign-based JSON API, accepts since param
│   └── cninfo.py           # 巨潮资讯 - POST form announcements, accepts since param
├── core/                   # Business logic
│   ├── analyzer.py         # LLM analysis + mark-as-analyzed
│   ├── scheduler.py        # Single run() flow: fetch → analyze → push
│   └── feishu_pusher.py    # Feishu card message push
└── .github/workflows/      # CI automation
```

## Config

All config lives in `config.py` + `.env` loaded via `python-dotenv`.

- **AI providers** (probed in order): Gemini > DeepSeek > OpenAI-compat. Fallback = keyword classification only.
- **DATA_RETENTION_HOURS** (default 72): old data auto-deleted on each run.
- **NEWS_SOURCES**: dict in `config.py`. Each entry has source-specific URL/params.
- **NEWS_CATEGORIES**: substring keyword matching dict.
- `.env` is gitignored. GitHub Actions uses repo Secrets, not `.env`.

## Data Sources — Known State

| Source | Type | Status | Detail |
|--------|------|--------|--------|
| cls (财联社) | JSON API | ✅ incremental | Sign: SHA1→MD5 of sorted params. `last_time` set to `since` timestamp. Client-side ctime filter. |
| cninfo (巨潮资讯) | POST form | ✅ incremental + pagination | Sorted by `annDate desc`, client-side time filter with multi-page pull. |

Adding a new data source requires:
1. Entry in `config.py` `NEWS_SOURCES` dict
2. New source file with `collect(config, since=None) -> list[dict]`
3. Register module in `collectors/__init__.py` `_HANDLERS` dict

## CI / GitHub Actions

Single workflow: `.github/workflows/collect.yml`
- **Cron**: `*/5 * * * *` (triggers every 5 min, GH Actions max)
- **Loop**: inside job runs `--loop` mode with 60s interval, up to 6h per run
- **Cache**: `news.db` cached between runs via `actions/cache`, preventing re-fetch/re-analysis
- Secrets needed: `GEMINI_API_KEY`, `FEISHU_WEBHOOK_URL`, `STOCK_WATCHLIST` (as Variable or Secret)
- Env vars written to `.env` in CI via `echo`

## SQLite Schema

Auto-created `news.db` with two tables:
- `news(id TEXT PK, title, content, summary, source, source_name, url, category, sentiment, impact, related_stocks, ai_analysis, freshness TEXT DEFAULT 'medium', analyzed INTEGER DEFAULT 0, created_at, updated_at)`
- `reports(id INTEGER PK, type, title, content, created_at)` (保留, 未使用)

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

## Noteworthy

- Feishu card messages are interactive JSON, sent via webhook POST. No Feishu SDK.
- Data older than 72 hours is auto-deleted on each run (`DATA_RETENTION_HOURS`).
- cls `collect()` passes `since` as `last_time` API param — only gets items after that time.
- cninfo `collect()` paginates up to 5 pages, stops when items are older than `since`.
# A股概念发现与验证系统

实时采集财联社电报 + 巨潮资讯公告 → AI 事件识别 → **独立概念发现** → **7信号验证** → **风控决策** → TUI 终端看板。

```text
新闻/公告 → AI事件抽取 → 概念发现(candidate→observing→validated)
                              ↓
                  7信号验证(事件/资金/涨停/竞价/扩散/媒体/研报)
                              ↓
                  风控决策(主线参与 / 存疑观察 / 一日游回避) → TUI看板
```

## 项目结构

```
├── main.py                      # CLI入口 (run / init / tui)
├── collectors/                  # 数据源采集
│   ├── cls.py                   # 财联社 (签名API，增量拉取)
│   └── cninfo.py                # 巨潮资讯 (POST分页，增量拉取)
├── services/                    # 业务服务层 (8 modules)
│   ├── event_service.py         # AI事件识别 (LLM结构化JSON, concept_keywords)
│   ├── concept_discovery.py     # 概念发现引擎 (candidate→observing→validated)
│   ├── concept_validator.py     # 7信号验证 (>=5主线, 4存疑, <=3一日游)
│   ├── stock_validator.py       # 个股3步验证 (业务关联/公告/研报)
│   ├── capital_detector.py      # 资金异动 (涨停/龙虎榜/北向/竞价)
│   ├── market_monitor.py        # 市场监控 (大盘量能/板块/情绪)
│   ├── source_monitor.py        # 信息源监控 (Tier 1-6)
│   └── risk_control.py          # 风控引擎 (追高/事件支撑/量能/止损)
├── core/
│   ├── llm_client.py            # 统一 LLM 调用客户端
│   ├── db_init.py               # 双数据库初始化 (news.db 3表 + concept.db 12表)
│   └── scheduler.py             # SOP三阶段调度: 盘前/盘中/盘后
├── tui/                         # Textual TUI终端 (5页签)
│   ├── app.py                   # 主应用 (导航 1-5 + r刷新 + q退出)
│   ├── db.py                    # DB查询层
│   └── screens/
│       ├── dashboard.py         # 1: SOP阶段 + 概念验证摘要 + 风控 + 量能
│       ├── concepts_view.py     # 2: 概念候选池 (状态/生命周期/信号/verdict)
│       ├── validation_view.py   # 3: 7信号验证 + 概念评分 + 个股3步验证
│       ├── capital_view.py      # 4: 资金异动 + 涨停 + 龙虎榜 + 北向
│       └── sources_view.py      # 5: 信息源状态 + 风控总览 + 事件
├── tests/                       # 测试
│   ├── test_concept_discovery.py
│   ├── test_concept_validator.py
│   ├── test_capital_detector.py
│   └── test_risk_control.py
├── prd/                         # 产品需求文档
└── news.db + concept.db         # 双数据库分离
```

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 API Keys
# AI: Gemini (免费) / DeepSeek / OpenAI 兼容
# Tushare token 用于涨停/龙虎榜/北向/板块数据

# 3. 运行
python main.py run              # 单次增量采集+分析+概念发现
python main.py run --loop       # 持续循环采集 (默认5秒)
python main.py run --loop -i 30 # 每30秒轮询
python main.py init             # 检查配置
python main.py tui              # TUI终端
```

## TUI 终端操作

| 按键 | 功能 |
|------|------|
| `1` | Dashboard — SOP阶段 + 概念验证摘要 + 风控 + 量能 |
| `2` | Concepts — 概念候选池 (状态/生命周期/信号数/verdict) |
| `3` | Validation — 7信号验证 + 概念评分 + 个股3步验证 |
| `4` | Capital — 资金异动 + 涨停统计 + 龙虎榜 + 北向 |
| `5` | Sources — 信息源状态 + 风控总览 + 事件时间线 |
| `r` | 手动刷新当前页面 |
| `q` | 退出 |

## 核心功能

### 1. 数据采集
- 财联社电报 — 签名JSON API，`since` 参数增量拉取
- 巨潮资讯公告 — POST分页，客户端时间过滤
- 自动去重 + 72小时数据保留

### 2. AI事件识别
- LLM 结构化抽取（Gemini / DeepSeek / OpenAI）
- 8大事件类型：ORDER / EARNINGS / TECHNOLOGY / POLICY / MNA / CAPITAL / RISK / OTHER
- JSON 输出校验 + 3次重试
- 提取 concept_keywords 用于概念发现

### 3. 概念发现引擎
- 从 AI 事件抽取结果中自动发现概念关键词
- 三级生命周期：candidate → observing (≥3提及,≥2天) → validated (≥5提及)
- 衰减机制：72h无新增→DECLINING，7天→DEAD

### 4. 7信号验证
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

### 5. 个股3步验证
1. **业务关联度** — 概念角色 + 受益路径
2. **公告验证** — 近90天澄清/问询函
3. **研报验证** — 券商覆盖度

### 6. 风控引擎
- 追高风险（基于概念生命周期阶段）
- 事件支撑（无事件支撑的异动一律过滤）
- 大盘量能（两市<8000亿→风险）
- 止损规则（跌破5日/10日均线或-5%）

### 7. SOP三阶段调度
| 阶段 | 时间 | 动作 |
|------|------|------|
| Pre-market | 7:00-9:15 | 采集→事件抽取→概念发现→题材预判 |
| Intraday | 9:15-15:00 | 增量采集→资金异动→涨停监控→验证→风控 |
| Post-market | 15:00-22:00 | 涨停复盘→龙虎榜→北向→全量验证→评分→风控终检 |

### 8. 数据库架构
- **news.db**: news / reports / event_analysis (3表)
- **concept.db**: concept_candidate / concept_stock / concept_event / concept_validation / capital_anomaly / limitup_stats / dragon_tiger / northbound_flow / stock_validation / risk_check / concept_score / sop_log (12表)

## 数据源

| 来源 | 类型 | 说明 |
|------|------|------|
| 财联社 (cls.cn) | JSON API | SHA1→MD5 签名，增量拉取 |
| 巨潮资讯 (cninfo.com.cn) | POST | 分页查询，按公告日期排序 |
| Tushare | API | 涨停/龙虎榜/北向/板块数据 |

## 配置说明

配置文件 `.env`（参考 `.env.example`）:

| 变量 | 说明 |
|------|------|
| `GEMINI_API_KEY` | Google Gemini API Key（免费，推荐首选） |
| `DEEPSEEK_API_KEY` | DeepSeek API Key（极低成本） |
| `OPENAI_API_KEY` | OpenAI 兼容接口 Key |
| `TUSHARE_TOKEN` | Tushare 数据平台 Token |
| `DATA_RETENTION_HOURS` | 数据保留小时数（默认72） |
| `FETCH_INTERVAL_SECONDS` | 循环采集间隔秒数（默认5） |

## 技术栈

- **语言**: Python 3.10+
- **采集**: requests, beautifulsoup4
- **AI**: google-genai, openai (兼容 DeepSeek 等)
- **行情**: Tushare + AKShare
- **TUI**: Textual
- **数据库**: SQLite (双库: news.db + concept.db)
- **配置**: python-dotenv

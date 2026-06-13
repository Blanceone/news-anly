# A股智能选股终端 — 开发计划

> 基于 `prd/# A股智能选股终端（TUI版）开发计划 V1.md`，适配当前 Python 代码库。

## 总体架构

```
collectors/（已有）→ services/ → TUI Terminal（Textual）
                  ↘ SQLite → PostgreSQL（Phase 升级）
```

## Phase 1：数据流打通（1周）✅

| # | 任务 | 状态 |
|---|------|------|
| 1.1 | news-service（采集/去重/入库） | ✅ |
| 1.2 | event-service（LLM结构化事件抽取） | ✅ |
| 1.3 | event_analysis 表 | ✅ |
| 1.4 | 集成到采集管道 | ✅ |

---

## Phase 2：事件识别引擎（1周）✅

| # | 任务 | 状态 |
|---|------|------|
| 2.1 | 按 PRD 事件分类体系完善 Prompt | ✅ |
| 2.2 | 输出校验 + 重试机制（最多3次） | ✅ |
| 2.3 | 覆盖 8 大事件类型 | ✅ |

---

## Phase 3：股票关联 V1（1周）✅

| # | 任务 | 状态 |
|---|------|------|
| 3.1 | theme_stock_mapping 表（AI/算力/半导体/机器人/创新药 共31只） | ✅ |
| 3.2 | 事件自动关联受益股票 | ✅ |

---

## Phase 4：知识图谱 V1（2周）✅

| # | 任务 | 状态 |
|---|------|------|
| 4.1 | kg_entity + kg_relation + kg_direct_benefit 三表 | ✅ |
| 4.2 | CONTAINS/ENABLE/BENEFIT 关系体系 | ✅ |
| 4.3 | 初始数据（29实体/28关系/29直连受益） | ✅ |
| 4.4 | BFS多级推理引擎（最大深度4层） | ✅ |

---

## Phase 5：评分系统（1周）✅

V1 公式：`TotalScore = EventScore × 40% + BenefitScore × 60%`

| # | 任务 | 状态 |
|---|------|------|
| 5.1 | EventScore（S=100/A=80/B=60/C=40） | ✅ |
| 5.2 | BenefitScore（一级=95/二级=80/三级=60） | ✅ |
| 5.3 | TotalScore 综合评分（事件*40% + 受益*60%） | ✅ |
| 5.4 | stock_score / recommendation_result 表 | ✅ |
| 5.5 | TOP20 推荐榜输出 | ✅ |

---

## Phase 6：市场验证引擎（1周）

### 目标
解决"利好不涨"问题

### 任务
| # | 任务 |
|---|------|
| 6.1 | 行情数据采集（板块涨幅/涨停数/资金流向） |
| 6.2 | MarketConfirmation 评分 |

---

## Phase 7：TUI 终端 ✅

| # | 任务 | 状态 |
|---|------|------|
| 7.1 | Dashboard（实时新闻/热点题材/推荐股票） | ✅ |
| 7.2 | Theme View（主题排行/关联股票） | ✅ |
| 7.3 | Stock View（评分/受益逻辑/相关新闻） | ✅ |
| 7.4 | Event View（事件列表/详情/影响股票） | ✅ |
| 7.5 | main.py tui 命令 + 键盘导航 (1-4/r/q) | ✅ |

启动命令：`python main.py tui`

---

## Phase 8：历史回测（2周）

### 功能
历史事件回放 / 策略验证 / 收益统计

### 指标
胜率 / 收益率 / 最大回撤 / 夏普比率

---

## MVP 里程碑

```text
✅ 新闻采集
🔜 AI事件识别
⬜ 股票关联
⬜ 推荐引擎
⬜ TUI终端
```

## 数据库策略

V1 保持 SQLite，按 PRD schema 建表，后续迁移 PostgreSQL。

## 关键原则

1. AI 只负责结构化抽取，不做荐股
2. 评分由规则引擎执行
3. 产业链知识图谱是核心竞争力

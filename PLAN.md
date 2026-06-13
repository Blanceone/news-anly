# A股智能选股终端 — 开发计划

> 基于 `prd/# A股智能选股终端（TUI版）开发计划 V1.md`，适配当前 Python 代码库。

## 总体架构

```
collectors/（已有）→ services/ → TUI Terminal（Textual）
                  ↘ SQLite → PostgreSQL（Phase 升级）
```

## Phase 1：数据流打通（1周）← 现在开始

### 目标
新闻 → 事件 → 数据库

### 任务

| # | 任务 | 状态 |
|---|------|------|
| 1.1 | news-service（采集/去重/入库） | ✅ 已完成 |
| 1.2 | **event-service（LLM结构化事件抽取）** | 🔜 正在做 |
| 1.3 | event_analysis 表 + event_stock_mapping 表 | 待开始 |
| 1.4 | 集成到采集管道 | 待开始 |

### 验收标准
- 每秒条新闻可正确处理并生成结构化事件 JSON
- event_type/industry/sentiment/importance 字段完整

---

## Phase 2：事件识别引擎（1周）

### 目标
优化 Prompt，覆盖 8 大事件类型、准确率 80%+

### 事件类型
ORDER / EARNINGS / TECHNOLOGY / POLICY / MNA / CAPITAL / RISK / OTHER

### 任务
| # | 任务 |
|---|------|
| 2.1 | 按 PRD 事件分类体系完善 Prompt |
| 2.2 | 输出校验 + 重试机制 |
| 2.3 | 抽样 100 条测试准确率 |

---

## Phase 3：股票关联 V1（1周）

### 目标
事件 → 股票 映射

### 任务
| # | 任务 |
|---|------|
| 3.1 | theme_stock_mapping 表（AI/算力/半导体/机器人/创新药） |
| 3.2 | 事件自动关联受益股票 |

---

## Phase 4：知识图谱 V1（2周）

### 目标
主题 → 行业 → 技术 → 产品 → 股票 推理链

### 任务
| # | 任务 |
|---|------|
| 4.1 | 图谱节点表（Theme/Industry/Technology/Product/Stock） |
| 4.2 | 图谱关系表（CONTAINS/DEPENDS/SUPPLY/BENEFIT） |
| 4.3 | 初始数据填充（50~100 主题） |
| 4.4 | 多级受益推理引擎 |

---

## Phase 5：评分系统（1周）

### 公式
```
总分 = 事件强度 × 20% + 受益程度 × 30%
     + 市场验证 × 20% + 财务质量 × 15%
     + 技术趋势 × 10% + 资金流向 × 5%
```

### 任务
| # | 任务 |
|---|------|
| 5.1 | EventScore（S=100/A=80/B=60/C=40） |
| 5.2 | BenefitScore（一级=95/二级=80/三级=60） |
| 5.3 | TotalScore 综合评分 |
| 5.4 | TOP20 推荐榜输出 |

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

## Phase 7：TUI 终端（1周）

### 框架
Python Textual

### 页面
- Dashboard（实时新闻/热点题材/推荐股票）
- Theme View（主题排行/资金流向/关联股票）
- Stock View（评分/受益逻辑/相关新闻）
- Event View（事件列表/详情/影响股票）

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

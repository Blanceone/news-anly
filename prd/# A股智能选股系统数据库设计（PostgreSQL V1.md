# A股智能选股系统数据库设计（PostgreSQL V1.0）

## 1. 设计原则

### 核心目标

支持：

* 新闻采集
* 公告采集
* 股票画像
* 产业链知识库
* AI事件分析
* 股票评分
* 热点题材
* 历史回测

---

### 数据分层

```text
ODS层（原始数据）
│
├── 新闻
├── 公告
├── 行情
│
DWD层（清洗数据）
│
├── 事件
├── 股票画像
├── 产业链
│
DWS层（分析结果）
│
├── 股票评分
├── 热点题材
├── 推荐结果
```

---

# 2. 股票基础表

## stock_basic

股票基础信息

```sql
CREATE TABLE stock_basic (
    stock_code VARCHAR(10) PRIMARY KEY,
    stock_name VARCHAR(50) NOT NULL,

    exchange VARCHAR(10),
    industry VARCHAR(100),
    sub_industry VARCHAR(100),

    market_value NUMERIC(20,2),

    is_st BOOLEAN DEFAULT FALSE,

    list_date DATE,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

---

### 示例

```json
{
  "stock_code":"002031",
  "stock_name":"巨轮智能",
  "industry":"机械设备",
  "sub_industry":"机器人"
}
```

---

# 3. 股票画像表

## stock_profile

维护知识图谱

```sql
CREATE TABLE stock_profile (
    id BIGSERIAL PRIMARY KEY,

    stock_code VARCHAR(10),

    themes JSONB,

    suppliers JSONB,

    customers JSONB,

    products JSONB,

    description TEXT,

    updated_at TIMESTAMP DEFAULT NOW()
);
```

---

### 示例

```json
{
  "themes":[
    "机器人",
    "减速器",
    "智能制造"
  ],

  "products":[
    "RV减速器"
  ]
}
```

---

# 4. 新闻原始表

## news_raw

保存所有原始新闻

```sql
CREATE TABLE news_raw (
    id BIGSERIAL PRIMARY KEY,

    source VARCHAR(50),

    title TEXT,

    content TEXT,

    publish_time TIMESTAMP,

    source_url TEXT,

    created_at TIMESTAMP DEFAULT NOW()
);
```

---

### 索引

```sql
CREATE INDEX idx_news_publish_time
ON news_raw(publish_time);

CREATE INDEX idx_news_source
ON news_raw(source);
```

---

# 5. 公告原始表

## announcement_raw

```sql
CREATE TABLE announcement_raw (
    id BIGSERIAL PRIMARY KEY,

    stock_code VARCHAR(10),

    stock_name VARCHAR(50),

    title TEXT,

    content TEXT,

    publish_time TIMESTAMP,

    announcement_type VARCHAR(100),

    source_url TEXT,

    created_at TIMESTAMP DEFAULT NOW()
);
```

---

# 6. AI事件表

## event_analysis

核心表

所有新闻和公告最终进入这里

```sql
CREATE TABLE event_analysis (
    event_id BIGSERIAL PRIMARY KEY,

    source_type VARCHAR(20),

    source_id BIGINT,

    event_type VARCHAR(50),

    industry VARCHAR(100),

    sub_industry VARCHAR(100),

    sentiment VARCHAR(20),

    importance VARCHAR(10),

    novelty_score INTEGER,

    event_score INTEGER,

    ai_summary TEXT,

    created_at TIMESTAMP DEFAULT NOW()
);
```

---

### 示例

```json
{
  "event_type":"技术突破",
  "industry":"半导体",
  "sub_industry":"先进封装",
  "sentiment":"positive",
  "importance":"A",
  "event_score":88
}
```

---

# 7. 事件关联股票表

## event_stock_mapping

一个事件可能影响多只股票

```sql
CREATE TABLE event_stock_mapping (
    id BIGSERIAL PRIMARY KEY,

    event_id BIGINT,

    stock_code VARCHAR(10),

    benefit_level INTEGER,

    benefit_score INTEGER,

    relation_type VARCHAR(50),

    created_at TIMESTAMP DEFAULT NOW()
);
```

---

### relation_type

```text
一级受益
二级受益
三级受益
概念关联
```

---

# 8. 产业链知识库

## industry_chain

```sql
CREATE TABLE industry_chain (
    id BIGSERIAL PRIMARY KEY,

    theme_name VARCHAR(100),

    industry VARCHAR(100),

    stock_code VARCHAR(10),

    benefit_level INTEGER,

    description TEXT,

    updated_at TIMESTAMP DEFAULT NOW()
);
```

---

### 示例

```json
{
  "theme_name":"先进封装",
  "stock_code":"002156",
  "benefit_level":1
}
```

---

# 9. 热点题材表

## theme_heat

实时统计

```sql
CREATE TABLE theme_heat (
    id BIGSERIAL PRIMARY KEY,

    theme_name VARCHAR(100),

    news_count INTEGER,

    limit_up_count INTEGER,

    inflow_amount NUMERIC(20,2),

    heat_score INTEGER,

    stat_date DATE,

    created_at TIMESTAMP DEFAULT NOW()
);
```

---

# 10. 财务指标表

## financial_indicator

```sql
CREATE TABLE financial_indicator (
    id BIGSERIAL PRIMARY KEY,

    stock_code VARCHAR(10),

    report_date DATE,

    roe NUMERIC(10,2),

    gross_margin NUMERIC(10,2),

    debt_ratio NUMERIC(10,2),

    profit_growth NUMERIC(10,2),

    operating_cashflow NUMERIC(20,2),

    created_at TIMESTAMP DEFAULT NOW()
);
```

---

# 11. 行情快照表

## market_snapshot

分钟级数据

```sql
CREATE TABLE market_snapshot (
    id BIGSERIAL PRIMARY KEY,

    stock_code VARCHAR(10),

    trade_time TIMESTAMP,

    price NUMERIC(10,2),

    volume BIGINT,

    turnover NUMERIC(20,2),

    turnover_rate NUMERIC(10,2),

    change_percent NUMERIC(10,2)
);
```

---

### 分区建议

```sql
PARTITION BY RANGE(trade_time)
```

按月分区。

---

# 12. 资金流向表

## capital_flow

```sql
CREATE TABLE capital_flow (
    id BIGSERIAL PRIMARY KEY,

    stock_code VARCHAR(10),

    trade_date DATE,

    main_inflow NUMERIC(20,2),

    northbound_inflow NUMERIC(20,2),

    龙虎榜净买入 NUMERIC(20,2),

    created_at TIMESTAMP DEFAULT NOW()
);
```

---

# 13. 市场验证结果表

## market_confirmation

验证市场是否认可某事件

```sql
CREATE TABLE market_confirmation (
    id BIGSERIAL PRIMARY KEY,

    event_id BIGINT,

    sector_change NUMERIC(10,2),

    capital_inflow NUMERIC(20,2),

    limit_up_count INTEGER,

    confirmation_score INTEGER,

    calculated_at TIMESTAMP DEFAULT NOW()
);
```

---

# 14. 股票评分表

## stock_score

最核心业务表

```sql
CREATE TABLE stock_score (
    id BIGSERIAL PRIMARY KEY,

    stock_code VARCHAR(10),

    score_date DATE,

    event_score INTEGER,

    benefit_score INTEGER,

    market_score INTEGER,

    financial_score INTEGER,

    technical_score INTEGER,

    capital_score INTEGER,

    total_score INTEGER,

    created_at TIMESTAMP DEFAULT NOW()
);
```

---

### 索引

```sql
CREATE INDEX idx_stock_score_rank
ON stock_score(score_date,total_score DESC);
```

---

# 15. 推荐结果表

## recommendation_result

最终输出

```sql
CREATE TABLE recommendation_result (
    id BIGSERIAL PRIMARY KEY,

    stock_code VARCHAR(10),

    strategy_type VARCHAR(20),

    rank_no INTEGER,

    score INTEGER,

    recommendation_reason TEXT,

    created_at TIMESTAMP DEFAULT NOW()
);
```

---

### strategy_type

```text
SHORT
LONG
```

---

# 16. 历史回测表

## backtest_result

```sql
CREATE TABLE backtest_result (
    id BIGSERIAL PRIMARY KEY,

    strategy_name VARCHAR(100),

    trade_date DATE,

    stock_code VARCHAR(10),

    buy_price NUMERIC(10,2),

    sell_price NUMERIC(10,2),

    holding_days INTEGER,

    return_rate NUMERIC(10,2),

    created_at TIMESTAMP DEFAULT NOW()
);
```

---

# 17. Redis缓存设计

## 实时新闻

```text
news:latest
```

---

## 实时热点

```text
theme:heat
```

---

## 实时排行榜

```text
rank:short
rank:long
```

---

## 股票实时评分

```text
stock:score:{code}
```

---

# 18. Elasticsearch索引

## news_index

新闻全文检索

---

## announcement_index

公告全文检索

---

## event_index

事件检索

---

## stock_profile_index

股票画像检索

---

# 19. V1核心表

第一阶段必须完成：

```text
stock_basic
stock_profile

news_raw
announcement_raw

event_analysis
event_stock_mapping

industry_chain

stock_score
recommendation_result
```

这8张表即可支撑第一版系统上线。

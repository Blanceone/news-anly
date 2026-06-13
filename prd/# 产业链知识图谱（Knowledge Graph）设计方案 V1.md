# 产业链知识图谱（Knowledge Graph）设计方案 V1.0

## 1. 设计目标

### 解决的问题

新闻：

```text
华为发布半导体韬定律
```

传统系统：

```text
半导体
↓
关联300只股票
```

结果：

```text
噪音极大
```

---

知识图谱系统：

```text
华为
↓
半导体
↓
先进封装
↓
长电科技
↓
受益程度 95
```

输出：

```text
TOP5真正受益股
```

---

# 2. 图谱整体架构

```text
事件(Event)
│
├── 影响主题(Theme)
│
├── 影响行业(Industry)
│
├── 影响技术(Technology)
│
└── 影响产品(Product)
         │
         ▼
产业链节点
         │
         ▼
上市公司(Stock)
```

---

# 3. 图谱实体设计

## 一级实体

### Event

事件

例如：

```text
华为发布韬定律
苹果发布Vision Pro
国家出台机器人政策
```

---

### Theme

主题

例如：

```text
机器人
AI
半导体
算力
创新药
低空经济
```

---

### Industry

行业

例如：

```text
半导体
光模块
EDA
先进封装
服务器
```

---

### Technology

技术

例如：

```text
Chiplet
HBM
CPO
先进封装
硅光
```

---

### Product

产品

例如：

```text
GPU
减速器
光模块
交换机
存储芯片
```

---

### Company

企业

例如：

```text
华为
英伟达
比亚迪
宁德时代
```

---

### Stock

上市公司

例如：

```text
长电科技
通富微电
中际旭创
巨轮智能
```

---

# 4. 图谱关系设计

## Event → Theme

```text
华为发布韬定律
    ↓
半导体
```

关系：

```text
AFFECT_THEME
```

---

## Theme → Industry

```text
半导体
 ↓
先进封装
```

关系：

```text
CONTAINS_INDUSTRY
```

---

## Industry → Technology

```text
先进封装
 ↓
Chiplet
```

关系：

```text
CONTAINS_TECH
```

---

## Technology → Product

```text
Chiplet
 ↓
封装服务
```

关系：

```text
ENABLE_PRODUCT
```

---

## Product → Stock

```text
先进封装
 ↓
长电科技
```

关系：

```text
BENEFIT_STOCK
```

---

# 5. 股票节点设计

## Stock Node

```json
{
  "stock_code":"600584",
  "stock_name":"长电科技",

  "industry":"半导体",

  "market_value":1000,

  "roe":15.5,

  "themes":[
    "先进封装",
    "Chiplet"
  ]
}
```

---

# 6. 核心关系权重

这是最关键部分。

不是所有关系都一样。

---

## 示例

```text
先进封装
 ↓
长电科技
```

关系：

```text
BENEFIT_STOCK
```

权重：

```text
95
```

---

```text
先进封装
 ↓
某概念股
```

权重：

```text
20
```

---

# 7. Benefit Weight设计

## 一级受益

核心龙头

```text
90~100
```

示例：

```text
HBM
 ↓
香农芯创
```

---

## 二级受益

重要参与者

```text
70~89
```

---

## 三级受益

产业链配套

```text
40~69
```

---

## 概念关联

蹭热点

```text
0~39
```

---

# 8. Neo4j图数据库设计

推荐使用：

```text
Neo4j
```

原因：

产业链天然是图结构。

---

## 节点示例

```cypher
CREATE (:Theme {
    name:'半导体'
})

CREATE (:Technology {
    name:'先进封装'
})

CREATE (:Stock {
    code:'600584',
    name:'长电科技'
})
```

---

## 关系示例

```cypher
MATCH
(t:Theme{name:'半导体'}),
(tech:Technology{name:'先进封装'})

CREATE (t)-[:CONTAINS_TECH]->(tech)
```

---

```cypher
MATCH
(tech:Technology{name:'先进封装'}),
(stock:Stock{name:'长电科技'})

CREATE (tech)-[:BENEFIT_STOCK{
weight:95
}]->(stock)
```

---

# 9. 图谱推理引擎

## 输入

新闻：

```text
华为发布半导体韬定律
```

---

AI输出：

```json
{
 "theme":"半导体",
 "technology":"先进封装"
}
```

---

图谱查询：

```cypher
MATCH
(t:Technology{name:'先进封装'})
-[r:BENEFIT_STOCK]->
(stock)

RETURN stock,r.weight
ORDER BY r.weight DESC
```

---

输出：

| 股票   | 权重 |
| ---- | -- |
| 长电科技 | 95 |
| 通富微电 | 92 |
| 华天科技 | 80 |

---

# 10. 多跳推理

这是未来最强能力。

---

一级推理：

```text
事件
 ↓
技术
 ↓
股票
```

---

二级推理：

```text
事件
 ↓
技术
 ↓
产品
 ↓
股票
```

---

三级推理：

```text
事件
 ↓
主题
 ↓
行业
 ↓
技术
 ↓
股票
```

---

# 11. 图谱自动更新

## 来源

### 新闻

发现新关系：

```text
华为采用某公司产品
```

---

### 公告

发现：

```text
新增客户
新增供应商
```

---

### 年报

发现：

```text
前五大客户
前五大供应商
```

---

自动更新图谱。

---

# 12. 图谱评分系统

最终受益分：

```text
Benefit Score
=
关系权重
×
路径可信度
×
主题热度
```

---

示例：

```text
长电科技

关系权重 = 95

主题热度 = 90

可信度 = 0.95
```

结果：

```text
95 × 0.95 × 0.90

≈ 81
```

---

# 13. V1重点建设领域

优先不要做全市场。

先覆盖：

```text
AI
算力
半导体
先进封装
光模块
机器人
低空经济
创新药
新能源
军工
```

约：

```text
50~100个主题
```

---

覆盖：

```text
300~500家核心上市公司
```

即可支撑系统运行。

---

# 14. V2升级

增加：

## 客户关系图谱

```text
华为
↓
供应商
↓
上市公司
```

---

## 产品关系图谱

```text
产品A
↓
依赖产品B
↓
依赖产品C
```

---

## 竞争关系图谱

```text
中际旭创
↔
新易盛
```

---

## 替代关系图谱

```text
进口芯片
↓
国产替代
↓
受益公司
```

---

# 15. 最终架构

```text
新闻
↓
LLM事件识别
↓
知识图谱推理
↓
受益公司排序
↓
市场验证
↓
评分引擎
↓
TOP榜单
```

最终目标：

> 让系统能够从一条新闻出发，在10秒内自动找到真正受益的公司，而不是简单返回一个概念板块。

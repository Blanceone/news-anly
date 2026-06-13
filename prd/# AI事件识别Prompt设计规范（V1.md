# AI事件识别Prompt设计规范（V1.0）

## 1. 目标

### 系统定位

AI不是分析师。

AI不是投资顾问。

AI不是股票推荐器。

AI仅负责：

```text
新闻
↓
事件提取
↓
结构化输出
```

---

### 输出要求

输入：

```text
华为发布半导体韬定律
```

输出：

```json
{
  "event_type":"技术突破",
  "industry":"半导体",
  "sub_industry":"先进封装",
  "sentiment":"positive",
  "importance":"A",
  "novelty_score":85
}
```

后续全部由规则引擎处理。

---

# 2. LLM职责边界

AI负责：

* 事件分类
* 情绪分析
* 实体识别
* 行业识别
* 金额提取
* 时间提取
* 技术关键词提取
* 影响范围判断

---

AI禁止负责：

* 推荐股票
* 买卖建议
* 预测涨跌
* 生成目标价
* 直接评分股票

---

# 3. 输出JSON规范

统一格式：

```json
{
  "event_type":"",
  "event_subtype":"",

  "industry":"",
  "sub_industry":"",

  "sentiment":"",
  "importance":"",

  "entities":[],

  "amount":0,

  "amount_unit":"",

  "time_reference":"",

  "keywords":[],

  "summary":"",

  "reason":""
}
```

---

# 4. Event Type分类体系

## 一级分类

### 订单类

```text
ORDER
```

子分类：

```text
重大订单
长期订单
海外订单
战略合作
中标项目
```

---

### 业绩类

```text
EARNINGS
```

子分类：

```text
业绩预增
业绩预减
业绩快报
年报
季报
```

---

### 技术突破

```text
TECHNOLOGY
```

子分类：

```text
技术突破
新工艺
新产品
技术认证
专利
```

---

### 政策催化

```text
POLICY
```

子分类：

```text
国家政策
地方政策
行业规范
补贴
```

---

### 并购重组

```text
MNA
```

子分类：

```text
收购
兼并
资产重组
借壳
```

---

### 股东行为

```text
CAPITAL
```

子分类：

```text
增持
减持
回购
股权激励
```

---

### 风险事件

```text
RISK
```

子分类：

```text
处罚
诉讼
问询函
安全事故
退市风险
```

---

# 5. 情绪分析规范

## Positive

利好：

```text
positive
```

示例：

```text
签订订单
技术突破
业绩增长
国家政策支持
```

---

## Neutral

中性：

```text
neutral
```

示例：

```text
召开会议
发布公告
日常事项
```

---

## Negative

利空：

```text
negative
```

示例：

```text
减持
处罚
诉讼
亏损
```

---

# 6. Importance等级

## S级

重大事件

```text
S
```

示例：

* 国家级产业政策
* 千亿级项目
* 行业颠覆性技术

---

## A级

重大催化

```text
A
```

示例：

* 重大订单
* 核心技术突破
* 超预期业绩

---

## B级

普通利好

```text
B
```

示例：

* 一般合作
* 产品发布

---

## C级

影响较小

```text
C
```

---

# 7. 实体识别规范

必须提取：

## 公司

```json
{
  "type":"company",
  "name":"华为"
}
```

---

## 股票

```json
{
  "type":"stock",
  "name":"长电科技"
}
```

---

## 技术

```json
{
  "type":"technology",
  "name":"先进封装"
}
```

---

## 行业

```json
{
  "type":"industry",
  "name":"半导体"
}
```

---

# 8. 金额提取规范

示例：

```text
公司获得20亿元订单
```

输出：

```json
{
  "amount":20,
  "amount_unit":"亿元"
}
```

---

如果没有金额：

```json
{
  "amount":0
}
```

---

# 9. Novelty评分规范

目的：

判断新闻是否属于新催化。

评分：

```text
0~100
```

---

参考规则：

| 情况    | 分数     |
| ----- | ------ |
| 已反复报道 | 10~30  |
| 普通更新  | 40~60  |
| 首次披露  | 70~90  |
| 行业首创  | 90~100 |

---

# 10. 标准Prompt模板

## System Prompt

你是一名专业财经事件抽取助手。

你的任务：

从新闻中提取结构化事件信息。

禁止：

* 推荐股票
* 分析买卖
* 判断股价

必须：

* 输出标准JSON
* 不输出解释
* 不输出Markdown

事件类型必须从以下集合中选择：

ORDER
EARNINGS
TECHNOLOGY
POLICY
MNA
CAPITAL
RISK
OTHER

---

## User Prompt模板

请分析以下财经新闻：

标题：
{title}

正文：
{content}

按照指定JSON格式返回结果。

---

# 11. 输出示例

## 示例1

输入：

```text
华为发布半导体韬定律
```

输出：

```json
{
  "event_type":"TECHNOLOGY",
  "event_subtype":"技术突破",

  "industry":"半导体",
  "sub_industry":"先进封装",

  "sentiment":"positive",

  "importance":"A",

  "entities":[
    {
      "type":"company",
      "name":"华为"
    }
  ],

  "amount":0,

  "amount_unit":"",

  "keywords":[
    "半导体",
    "先进封装",
    "时间缩微",
    "韬定律"
  ],

  "novelty_score":85,

  "summary":"华为发布新的半导体技术路线",

  "reason":"属于技术创新事件"
}
```

---

# 12. 输出校验机制

LLM返回后必须校验：

## JSON合法性

检查：

```text
是否可解析
```

---

## 字段完整性

必须存在：

```text
event_type
industry
sentiment
importance
summary
```

---

## 类型校验

例如：

```text
importance
```

必须属于：

```text
S
A
B
C
```

否则自动重试。

---

# 13. V2升级方向

未来可增加：

## 多事件识别

一条新闻多个事件：

```text
订单
+
增持
+
扩产
```

---

## 事件因果链识别

例如：

```text
政策出台
↓
行业受益
↓
公司受益
```

---

## 自动产业链推理

例如：

```text
华为发布新技术
↓
先进封装
↓
长电科技
```

自动完成推理链路。

---

# 14. 最佳实践

推荐采用：

```text
LLM负责理解
+
规则负责决策
```

而不是：

```text
LLM负责理解
+
LLM负责推荐
```

原则：

> AI负责结构化，规则引擎负责投资逻辑。

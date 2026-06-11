# 行业拥挤度辅助层 V1 字段映射

## 1. 目标

这份文档只回答三件事：

1. `吸筹率 / 拥挤度` 要用哪些字段来算
2. 最小版 `过热预警 / 过热退潮` 先怎么判
3. 这些字段准备挂到现有扫描链的哪个位置

它不负责改主策略，只负责把：

- [industry_crowding_filter_v1.md](/D:/CC/Industry%20Insight/industry_crowding_filter_v1.md)

落成可执行的数据口径。

---

## 2. 接入位置

当前推荐顺序：

1. 先运行主扫描
   - 前置分流
   - 结构层
   - 突破层
   - 龙头层
2. 得到主标签
3. 再计算拥挤度辅助字段
4. 最后补一个辅助标签

所以它是：

**后置辅助层**

不是：

**前置替代层**

---

## 3. MVP 原则

V1 先做最小可用版，不一上来就把所有“拥挤度”维度都接齐。

先只接三类信息：

1. 行业吸筹率
2. 行业吸筹率历史分位
3. 高吸筹率下的退潮信号

先不接：

- 融资盘占比
- 更复杂的乖离率体系
- 更复杂的板块扩散/收缩广度指标

---

## 4. 字段映射总表

| 字段 | 含义 | 公式 / 口径 | 数据源 | 用途 |
| --- | --- | --- | --- | --- |
| `industry_amount` | 行业当日成交额 | 行业日线 `amount` | `sw_daily` | 计算吸筹率 |
| `market_amount` | 全市场当日成交额 | 全市场个股 `amount` 汇总 | `daily` | 计算吸筹率 |
| `absorption_rate` | 吸筹率 | `industry_amount / market_amount` | 派生 | 核心拥挤度字段 |
| `absorption_rate_rank_pct` | 吸筹率历史分位 | 行业吸筹率滚动历史分位 | 派生 | 判断过热程度 |
| `absorption_rate_zscore` | 吸筹率偏离强度 | 相对历史均值的标准差偏离 | 派生 | 可选增强字段 |
| `absorption_rate_5d_change` | 5日吸筹率变化 | 近5日吸筹率增减 | 派生 | 识别快速升温 |
| `leader_top1_pct_change` | 龙头当日涨跌 | 已有字段 | 现有龙头层 | 判断退潮 |
| `leader_follow_ok` | 龙头持续性 | 已有字段 | 现有龙头层 | 判断退潮 |
| `leader_top1_above_ma60` | 龙头中期趋势位置 | 已有字段 | 现有龙头层 | 判断退潮 |
| `final_label` | 主策略标签 | 已有字段 | 主策略输出 | 决定拥挤标签怎么解释 |
| `crowding_label` | 拥挤度辅助标签 | 新增字段 | 派生 | 后置提示 |

---

## 5. 核心数据来源

## 5.1 行业成交额

字段：

- `industry_amount`

来源：

- `sw_daily.amount`

说明：

- 当前我们已经在用 `sw_daily` 做二级行业历史
- 所以二级行业口径下，可以直接用同一条历史底库

当前可直接复用：

- [sw_daily_full_history.csv](/D:/CC/Industry%20Insight/.cache_scan_v2/sw_daily_full_history.csv)

## 5.2 全市场成交额

字段：

- `market_amount`

来源：

- `daily(trade_date=...)`

口径：

- 把当日全市场个股 `amount` 求和

说明：

- 这个值最好按交易日缓存
- 不需要按行业重复计算
- 一天算一次即可

---

## 6. 吸筹率字段定义

## 6.1 当日吸筹率

字段：

- `absorption_rate`

公式：

- `absorption_rate = industry_amount / market_amount`

说明：

- 这是最核心字段
- 不要一开始就做过多变体

## 6.2 历史分位

字段：

- `absorption_rate_rank_pct`

公式：

- 用当前行业过去一段历史的 `absorption_rate` 序列
- 计算当日值在历史序列里的分位

建议窗口：

- **先用滚动 252 个交易日**

原因：

- 和当前主策略里 `ma250 / 年线` 的时间感接近
- 也更适合识别“过去一年是否极热”

## 6.3 五日变化

字段：

- `absorption_rate_5d_change`

公式：

- `今日吸筹率 - 5日前吸筹率`

用途：

- 识别“是不是短时间迅速变挤”

---

## 7. 拥挤标签 V1 规则

## 7.1 拥挤正常

条件：

- `absorption_rate_rank_pct < 0.80`

输出：

- `crowding_label = 拥挤正常`

## 7.2 拥挤偏高

条件：

- `0.80 <= absorption_rate_rank_pct < 0.95`

输出：

- `crowding_label = 拥挤偏高`

## 7.3 过热预警

条件：

- `0.95 <= absorption_rate_rank_pct < 0.99`

输出：

- `crowding_label = 过热预警`

说明：

- 这时先不改主标签
- 只在榜单里提示“追高容错率下降”

## 7.4 过热退潮

条件分两段：

### 第一段：必须高吸筹率

- `absorption_rate_rank_pct >= 0.99`

### 第二段：再叠加退潮信号

满足以下任意一条即可：

- `leader_follow_ok == False`
- `leader_top1_pct_change <= 0`
- `leader_top1_above_ma60 == False`
- `absorption_rate_5d_change <= 0` 且吸筹率仍高位

输出：

- `crowding_label = 过热退潮`

---

## 8. 对主标签的修正原则

V1 先不直接改 `final_label`，而是做一个解释层规则。

## 8.1 不改标签，只降优先级

例如：

- `观察中 + 过热预警`
  - 保留 `观察中`
  - 但在榜单里标记为低优先级

- `趋势延续型偏强 + 过热预警`
  - 保留主标签
  - 但明确提示“高拥挤”

## 8.2 只有 `过热退潮` 才触发强修正

如果：

- 主标签属于
  - `观察中`
  - `接近启动`
  - `趋势延续型偏强`
- 且 `crowding_label == 过热退潮`

则解释层应明确写成：

- “不属于优先启动候选”
- “更像过热后的开始消退”

注意：

- V1 先不改 `final_label` 字段本身
- 先在 `summary_line` 或榜单备注里体现

---

## 9. 对现有扫描器的最小改造点

如果开始接代码，建议最先改这几处：

## 9.1 历史层

新增：

- `market_amount_by_date`

来源：

- 按交易日汇总 `daily.amount`

## 9.2 输入层

在现有 `StrategyInputs` 之外，新增一个拥挤度辅助输入结构更稳。

例如新建：

- `CrowdingInputs`

包含：

- `industry_code`
- `industry_name`
- `trade_date`
- `industry_amount`
- `market_amount`
- `absorption_rate`
- `absorption_rate_rank_pct`
- `absorption_rate_5d_change`
- `leader_top1_pct_change`
- `leader_follow_ok`
- `leader_top1_above_ma60`

## 9.3 输出层

在现有扫描结果 `csv` 上新增：

- `crowding_label`
- `crowding_note`

这样不会打乱主策略结构。

---

## 10. 最小实现优先级

真正写代码时，建议按这个顺序：

1. 先算 `industry_amount`
2. 再算 `market_amount`
3. 再算 `absorption_rate`
4. 再补 `absorption_rate_rank_pct`
5. 最后接 `过热退潮` 简化规则

不要一开始就做：

- 复杂广度指标
- 复杂多因子拥挤度总分
- 复杂自动降级系统

---

## 11. 当前最合理的落地方式

V1 最适合先做成：

**“现有二级行业主榜单上的拥挤度辅助列”**

而不是：

**新的独立评分系统**

这样既符合你的初衷，也能最快验证：

- 它到底能不能把那些“过热后开始消退”的行业识别出来

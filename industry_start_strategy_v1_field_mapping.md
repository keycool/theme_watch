# 行业启动策略 V1 字段映射表

## 1. 目的

这份文档把 [industry_start_strategy_v1.md](/D:/CC/Industry%20Insight/industry_start_strategy_v1.md) 拆成程序可落地的字段。

目标不是直接写代码，而是先回答四个问题：

1. 每个判断节点需要什么字段
2. 字段从哪个数据源来
3. 哪些字段能直接拿
4. 哪些字段需要计算、哪些仍需要人工解释

---

## 2. 字段分层

按策略顺序，字段分成五层：

1. 前置分流字段
2. 板块整理结构字段
3. 板块突破行为字段
4. 龙头确认字段
5. 最终标签字段

---

## 3. 前置分流字段

## 3.1 目标

先判断一个行业属于：

- `启动识别对象`
- `趋势延续对象`

这是后续所有判断的入口。

## 3.2 字段表

| 字段名 | 含义 | 来源 | 类型 | 说明 |
| --- | --- | --- | --- | --- |
| `industry_code` | 行业代码 | `sw_index_classify` / 人工映射 | 原始字段 | 例如 `801120.SI` |
| `industry_name` | 行业名称 | `sw_index_classify` / 人工映射 | 原始字段 | 例如 `食品饮料` |
| `latest_close` | 板块最新收盘价 | `sw_daily.close` | 原始字段 | 板块层核心价格 |
| `ma250` | 板块 250 日均线 | `sw_daily.close` 计算 | 计算字段 | 用于高位趋势排除与突破判断 |
| `ret_120d` | 板块近 120 日涨幅 | `sw_daily.close` 计算 | 计算字段 | 用于分位排序 |
| `ret_120d_rank_pct` | 板块近 120 日涨幅分位 | 全行业 `ret_120d` 横向排名 | 计算字段 | 用于判断是否已是热门主线 |
| `close_to_120d_high_ratio` | 最新价相对近 120 日高点比例 | `sw_daily.close` 计算 | 计算字段 | `latest_close / 120日最高收盘价` |
| `leaders_above_ma60_ratio` | 核心龙头站上 60 日均线比例 | `TDX MCP` / 个股历史 | 计算字段 | 反映核心龙头整体趋势位置 |
| `leaders_above_ma250_ratio` | 核心龙头站上 250 日均线比例 | `TDX MCP` / 个股历史 | 计算字段 | 反映是否已进入中长期强势 |
| `prefilter_hit_count` | 命中的高位趋势条件数 | 上述字段聚合 | 计算字段 | 用于前置分流 |
| `prefilter_label` | 前置分流结果 | 规则判定 | 规则字段 | `启动识别对象` / `趋势延续对象` |

## 3.3 前置分流规则映射

### 规则 P1：高位强趋势排除

建议程序条件：

| 条件编号 | 表达式 |
| --- | --- |
| `P1_1` | `latest_close > ma250 * 1.15` |
| `P1_2` | `ret_120d_rank_pct >= 0.80` |
| `P1_3` | `close_to_120d_high_ratio >= 0.95` |
| `P1_4` | `leaders_above_ma60_ratio >= 0.67 and leaders_above_ma250_ratio >= 0.67` |

建议判定：

- `prefilter_hit_count = P1_1 + P1_2 + P1_3 + P1_4`
- 如果 `prefilter_hit_count >= 2`：
  - `prefilter_label = 趋势延续对象`
- 否则：
  - `prefilter_label = 启动识别对象`

## 3.4 趋势延续体系标签映射

如果进入 `趋势延续对象`，再细分：

| 字段名 | 含义 | 建议逻辑 |
| --- | --- | --- |
| `trend_extension_strength` | 趋势延续强度 | `偏强` / `强势` |

建议判定：

- 若 `P1_1`、`P1_2`、`P1_4` 同时较强，且龙头层一致性高：
  - `趋势延续型强势`
- 否则：
  - `趋势延续型偏强`

---

## 4. 板块整理结构字段

这一层只对 `prefilter_label = 启动识别对象` 的行业生效。

## 4.1 字段表

| 字段名 | 含义 | 来源 | 类型 | 说明 |
| --- | --- | --- | --- | --- |
| `close_120d_high` | 近 120 日最高收盘价 | `sw_daily.close` 计算 | 计算字段 | A1 使用 |
| `close_120d_low` | 近 120 日最低收盘价 | `sw_daily.close` 计算 | 计算字段 | A3 使用 |
| `close_40d_low` | 近 40 日最低收盘价 | `sw_daily.close` 计算 | 计算字段 | A3 使用 |
| `range_first_80` | 前 80 日振幅 | `sw_daily.high/low/close` 计算 | 计算字段 | A2 使用 |
| `range_last_40` | 后 40 日振幅 | `sw_daily.high/low/close` 计算 | 计算字段 | A2 使用 |
| `a1_low_zone_ok` | 是否处于低位区间 | 规则判定 | 规则字段 | A1 |
| `a2_contraction_ok` | 是否振幅收敛 | 规则判定 | 规则字段 | A2 |
| `a3_no_new_low_ok` | 是否不再创新低 | 规则判定 | 规则字段 | A3 |
| `a4_not_hot_ok` | 是否阶段涨幅不居前 | 规则判定 | 规则字段 | A4 |
| `structure_score` | 结构层得分 | 规则聚合 | 计算字段 | 可用于调试 |
| `structure_ok` | 板块整理结构是否成立 | 规则聚合 | 规则字段 | 进入下一层的关键条件 |

## 4.2 规则映射

| 规则 | 建议表达式 |
| --- | --- |
| `A1` | `latest_close <= close_120d_high * 0.85` |
| `A2` | `range_last_40 <= range_first_80 * 0.90` |
| `A3` | `close_40d_low >= close_120d_low * 1.02` |
| `A4` | `ret_120d_rank_pct <= 0.40` |

建议判定：

- `structure_score = A1 + A2 + A3 + A4`
- `structure_ok = (A1 and A2 and A3 and A4)`

---

## 5. 板块突破行为字段

## 5.1 字段表

| 字段名 | 含义 | 来源 | 类型 | 说明 |
| --- | --- | --- | --- | --- |
| `amount_latest` | 最新成交额 | `sw_daily.amount` | 原始字段 | B2 使用 |
| `amount_ma20` | 20 日平均成交额 | `sw_daily.amount` 计算 | 计算字段 | B2 使用 |
| `close_ma250_ratio` | 收盘价相对年线比例 | `latest_close / ma250` | 计算字段 | B1 使用 |
| `amount_ma20_ratio` | 成交额相对 20 日均额比例 | `amount_latest / amount_ma20` | 计算字段 | B2 使用 |
| `recent_2d_above_ma250` | 最近 2 日是否都在年线上 | `sw_daily.close` 与 `ma250` | 计算字段 | B3 使用 |
| `above_ma250_3pct_streak` | 连续站上 `ma250 * 1.03` 的交易日数量 | `sw_daily.close` 与 `ma250` | 计算字段 | B4 使用 |
| `b1_above_ma250_ok` | 是否站上年线 | 规则判定 | 规则字段 | B1 |
| `b2_volume_breakout_ok` | 是否带量突破 | 规则判定 | 规则字段 | B2 |
| `b3_hold_above_ma250_ok` | 是否站稳年线 | 规则判定 | 规则字段 | B3 |
| `b4_new_breakout_ok` | 是否属于近期新突破 | 规则判定 | 规则字段 | B4 |
| `breakout_emerged` | 是否出现突破 | 规则聚合 | 规则字段 | B1+B2+B4 |
| `breakout_confirmed` | 是否确认突破 | 规则聚合 | 规则字段 | B1+B2+B3+B4 |

## 5.2 规则映射

| 规则 | 建议表达式 |
| --- | --- |
| `B1` | `close_ma250_ratio >= 1.03` |
| `B2` | `amount_ma20_ratio >= 1.20` |
| `B3` | `recent_2d_above_ma250 == True` |
| `B4` | `above_ma250_3pct_streak <= 20` |

建议判定：

- `breakout_emerged = B1 and B2 and B4`
- `breakout_confirmed = B1 and B2 and B3 and B4`

---

## 6. 龙头确认字段

## 6.1 字段表

| 字段名 | 含义 | 来源 | 类型 | 说明 |
| --- | --- | --- | --- | --- |
| `leader_candidates` | 龙头候选名单 | `TDX MCP` / `daily_basic` / 市值排序 | 计算字段 | 通常取前 3 或前 5 |
| `leader_count` | 龙头候选数量 | 同上 | 计算字段 | 用于检查覆盖度 |
| `leader_top1_name` | 第一龙头名 | 同上 | 计算字段 | 便于输出 |
| `leader_top1_pct_change` | 第一龙头当日涨跌幅 | `TDX MCP` / `daily` | 原始字段 | C2 使用 |
| `leader_top1_above_ma60` | 第一龙头是否站上 60 日均线 | `TDX MCP` | 规则字段 | C4 使用 |
| `leader_top1_above_ma250` | 第一龙头是否站上 250 日均线 | `TDX MCP` | 规则字段 | C4 使用 |
| `leader_5d_rank_pct` | 龙头近 5 日强度分位 | 个股历史 / TDX 面板 | 计算字段 | C2 使用 |
| `leader_follow_ok` | 龙头是否有持续性 | 个股次日/随后表现 | 规则字段 | C3 使用 |
| `leaders_above_ma60_count` | 龙头候选中站上 60 日均线数量 | `TDX MCP` | 计算字段 | 龙头一致性 |
| `leaders_above_ma250_count` | 龙头候选中站上 250 日均线数量 | `TDX MCP` | 计算字段 | 龙头一致性 |
| `c1_leaders_identified_ok` | 是否识别出龙头候选 | 规则判定 | 规则字段 | C1 |
| `c2_leader_outperform_ok` | 是否存在率先走强龙头 | 规则判定 | 规则字段 | C2 |
| `c3_leader_follow_ok` | 是否存在持续性 | 规则判定 | 规则字段 | C3 |
| `c4_leader_trend_ok` | 龙头趋势位置是否合格 | 规则判定 | 规则字段 | C4 |
| `leader_turning_strong_ok` | 龙头是否转强 | 规则聚合 | 规则字段 | C1+C2 |
| `leader_confirmed_ok` | 龙头是否确认 | 规则聚合 | 规则字段 | C1+C2+C3+C4 |

## 6.2 规则映射

| 规则 | 建议表达式 |
| --- | --- |
| `C1` | `leader_count >= 1` |
| `C2` | `leader_top1_pct_change >= 7` or `leader_5d_rank_pct >= 0.80` |
| `C3` | `leader_follow_ok == True` |
| `C4` | `leader_top1_above_ma60 == True` |

建议判定：

- `leader_turning_strong_ok = C1 and C2`
- `leader_confirmed_ok = C1 and C2 and C3 and C4`

说明：

- 如果后续增加“候选龙头中至少 2 只站上 60 日均线”的一致性要求，可以再增加一个 `C4_plus`。

---

## 7. 最终标签字段

## 7.1 启动识别标签映射

这一层只适用于：

- `prefilter_label = 启动识别对象`

| 字段名 | 含义 | 类型 |
| --- | --- | --- |
| `final_label` | 最终标签 | 规则字段 |
| `label_reason` | 标签原因摘要 | 解释字段 |
| `confidence_level` | 置信度 | 解释字段 |

## 7.2 建议映射规则

### `未启动`

满足任意一项即可：

- `structure_ok == False`
- `breakout_emerged == False`
- `leader_turning_strong_ok == False`

但这里建议加一个更细的实现顺序：

1. 若 `structure_ok == False` 且 `leader_turning_strong_ok == False`
   - `final_label = 未启动`
2. 若 `structure_ok == False` 但 `leader_turning_strong_ok == True`
   - `final_label = 观察中`

这样更贴近白酒、医药这类样本。

### `观察中`

满足任意一项：

- `structure_ok == True` and `breakout_emerged == False`
- `structure_ok == False` and `leader_turning_strong_ok == True`
- `breakout_emerged == True` and `leader_confirmed_ok == False`

### `接近启动`

同时满足：

- `structure_ok == True`
- `breakout_emerged == True`
- `leader_turning_strong_ok == True`

但以下至少一项未满足：

- `breakout_confirmed == False`
- `leader_confirmed_ok == False`

### `启动确认`

同时满足：

- `structure_ok == True`
- `breakout_confirmed == True`
- `leader_confirmed_ok == True`

---

## 8. 解释层字段

程序最后不能只给一个标签，最好同时吐出解释字段，便于写观察文章。

| 字段名 | 含义 | 用途 |
| --- | --- | --- |
| `summary_line` | 一句话摘要 | 直接用于结论段 |
| `structure_comment` | 板块结构解释 | 解释是否处于低位整理 |
| `breakout_comment` | 板块突破解释 | 解释是否完成突破 |
| `leader_comment` | 龙头解释 | 解释是否出现龙头带动 |
| `risk_comment` | 风险提示 | 提示数据不足或条件未闭合 |

示例：

- `白酒：观察中，偏弱，板块尚未突破，龙头仅局部活跃。`
- `医药：观察中，偏强，内部已有结构性走强，但核心龙头共振不足。`
- `半导体：趋势延续型强势，不属于启动识别对象。`

---

## 9. 当前最适合的程序化顺序

建议按这个顺序落代码：

1. 先实现前置分流字段
2. 再实现板块结构字段
3. 再实现板块突破字段
4. 最后实现龙头确认字段
5. 最终统一映射 `final_label`

原因是：

- 先把 `启动识别` 和 `趋势延续` 分开，能显著减少误判
- 后面的四档判断只服务于真正的启动型行业

---

## 10. 当前仍未完全自动化的部分

以下内容目前更适合先保留为“半自动”：

1. `leader_5d_rank_pct`
   - 需要更稳定的成分股短历史序列
2. `leader_follow_ok`
   - 需要至少多一日数据验证
3. `label_reason / summary_line`
   - 仍然建议程序生成底稿，再由规则模板整理成自然语言
4. `趋势延续型偏强` 与 `趋势延续型强势` 的细分
   - 目前更适合先做启发式规则，后续再调优

---

## 11. 这份映射表的意义

这份文档的作用是：

1. 把策略从“文章规则”翻成“程序字段”
2. 明确哪些判断依赖板块历史，哪些依赖龙头快照
3. 为后续代码改造提供稳定接口层

后面真正写程序时，应该优先围绕这份表，而不是再回到“先找一个行业试试看”的工作方式。

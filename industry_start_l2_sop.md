# 行业启动策略（二级行业版）SOP

## 1. 目标定位

- 这套系统抓的是“刚要起来”的细分行业，不是“已经很强”的细分行业。
- 输出分两层理解：
  - 内部观察口径：`未启动` / `观察中` / `接近启动` / `趋势延续型偏强` / `趋势延续型强势`
  - 严格确认口径：只有三条核心条件同时满足，才算 `启动确认`

## 2. 当前默认口径

- 行业层级：`申万二级行业`
- 主候选池门槛：`总市值 >= 2000亿`
- 历史数据源：`Tushare sw_daily`
- 龙头层数据：个股日线 + 成分股市值筛选

## 3. 为什么默认改成 2000 亿

- `1000亿` 适合试运行，但观察池偏宽。
- `2000亿` 更适合当前阶段：
  - 排除过小、易失真的二级行业
  - 保留更有代表性的细分赛道
  - 让候选池更接近“可跟踪、可执行”的状态

门槛对比参考：
- [sw_l2_threshold_comparison.md](/D:/CC/Industry%20Insight/sw_l2_threshold_comparison.md)

## 4. 关键规则文件

- 策略主文档：
  - [industry_start_strategy_v1.md](/D:/CC/Industry%20Insight/industry_start_strategy_v1.md)
- 字段映射：
  - [industry_start_strategy_v1_field_mapping.md](/D:/CC/Industry%20Insight/industry_start_strategy_v1_field_mapping.md)
- 规则引擎：
  - [industry_start_strategy_v1_engine.py](/D:/CC/Industry%20Insight/industry_start_strategy_v1_engine.py)

## 5. 运行顺序

### 第一步：确认历史底库

主历史缓存文件：
- [sw_daily_full_history.csv](/D:/CC/Industry%20Insight/.cache_scan_v2/sw_daily_full_history.csv)

要求：
- 至少覆盖 `250` 个交易日
- 目前已经满足

如果后面要继续补历史，可用：
```powershell
cd "D:\CC\Industry Insight"
py .\backfill_sw_daily_history.py --start-date 20240101 --end-date 20260630 --chunk-open-days 5 --max-new-fetches 1 --sleep-seconds 0
```

### 第二步：生成二级行业主候选池

脚本：
- [build_sw_l2_sample_pool.py](/D:/CC/Industry%20Insight/build_sw_l2_sample_pool.py)

运行：
```powershell
cd "D:\CC\Industry Insight"
py .\build_sw_l2_sample_pool.py
```

默认输出：
- [sw_l2_sample_pool.csv](/D:/CC/Industry%20Insight/sw_l2_sample_pool.csv)
- [sw_l2_sample_pool_summary.md](/D:/CC/Industry%20Insight/sw_l2_sample_pool_summary.md)

当前默认门槛已经是：
- `2000亿`

### 第三步：运行二级行业完整扫描

脚本：
- [run_sw_l2_strategy_scan.py](/D:/CC/Industry%20Insight/run_sw_l2_strategy_scan.py)

运行：
```powershell
cd "D:\CC\Industry Insight"
py .\run_sw_l2_strategy_scan.py
```

默认逻辑：
- 样本池：申万二级行业 + `2000亿`
- 板块层：结构 / 年线 / 成交额
- 龙头层：市值前 `3` 中的龙头强弱、趋势位置、持续性

## 6. 结果文件

### 标准输出

- 扫描明细：
  - [sw_l2_strategy_scan.csv](/D:/CC/Industry%20Insight/sw_l2_strategy_scan.csv)
- 扫描摘要：
  - [sw_l2_strategy_scan_summary.md](/D:/CC/Industry%20Insight/sw_l2_strategy_scan_summary.md)
- 分层榜单：
  - [sw_l2_strategy_leaderboard.md](/D:/CC/Industry%20Insight/sw_l2_strategy_leaderboard.md)

### 本次 2000 亿整固输出

这次因为原始 `csv` 被占用，额外落了一组独立文件：
- [sw_l2_strategy_scan_2000.csv](/D:/CC/Industry%20Insight/sw_l2_strategy_scan_2000.csv)
- [sw_l2_strategy_scan_summary_2000.md](/D:/CC/Industry%20Insight/sw_l2_strategy_scan_summary_2000.md)
- [sw_l2_strategy_leaderboard_2000.md](/D:/CC/Industry%20Insight/sw_l2_strategy_leaderboard_2000.md)

如果后面原文件不再被占用，标准输出即可继续覆盖更新。

## 7. 如何解读结果

### `趋势延续型偏强/强势`

- 代表行业已经走出较长趋势
- 不属于“刚启动”候选
- 应理解为强赛道跟踪对象，而不是启动识别对象

### `观察中`

- 代表已有局部转强线索
- 但三条核心条件还没有闭环
- 这是内部预警，不等于“已经启动”

### `接近启动`

- 代表结构、突破、龙头层已经更接近闭环
- 当前版本里还较少出现，说明规则仍偏严格

### `启动确认`

- 只有三条同时满足才成立：
  - 低位收敛结构成立
  - 板块带量突破年线成立
  - 龙头显著强势且持续性成立

## 8. 当前建议的工作节奏

每次更新时按这个顺序：

1. 检查历史底库是否需要回补
2. 重跑二级样本池
3. 重跑二级完整扫描
4. 优先查看：
   - `观察中`
   - `趋势延续型偏强`
5. 再从 `观察中` 里提炼重点跟踪名单

## 9. 当前版本的局限

- 低位收敛仍然是“日线量化代理”，还不是完整的周线图形识别
- `观察中` 行业可能仍偏多，需要后续继续优化阈值或做二次排序
- `启动确认` 目前偏严格，数量少是正常现象
- 当前版本还没有把“吸筹率 / 拥挤度”正式接进扫描链，所以对“过热后开始消退”的行业识别仍不够强

相关规则草案：
- [industry_crowding_filter_v1.md](/D:/CC/Industry%20Insight/industry_crowding_filter_v1.md)

## 10. 下一步默认衔接

这份 SOP 之后，默认下一步是：

- 基于 `2000亿` 口径
- 从 `观察中` 的二级行业里
- 再做一版更短的“重点跟踪名单”

如果继续升级系统，优先顺序建议是：

1. 接入“吸筹率 / 拥挤度辅助层”
2. 先作为辅助标签挂到现有榜单里
3. 再决定是否对 `观察中 / 接近启动` 做降级修正

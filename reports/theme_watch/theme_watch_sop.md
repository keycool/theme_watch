# ETF 主题观察 SOP

## 1. 定位

这套主题观察系统不是替代申万二级全市场扫描，而是把“我正在关注的 ETF / 主题指数”映射到最值得观察的申万二级行业。

核心目的：
- 从用户关注入口出发，而不是盲扫全市场。
- 用日收益相关性确认 ETF 与申万二级的对应关系。
- 最终仍回到申万二级图形页，观察年线、收敛路径、拥挤度和龙头状态。

## 2. 当前入口

优先打开总览页：
- [index.html](/D:/CC/Industry%20Insight/reports/theme_watch/index.html)

完整文字清单：
- [theme_to_sw_watchlist.md](/D:/CC/Industry%20Insight/reports/theme_watch/theme_to_sw_watchlist.md)

## 3. 新增 ETF 的标准流程

### 第一步：确认基金日线

默认优先尝试：

```powershell
py .\build_theme_to_sw_l2_correlation.py --ts-code 代码.SH --source fund --output .\reports\theme_watch\correlations\theme_代码_to_sw_l2_correlation.csv
```

深市 ETF 使用 `.SZ`：

```powershell
py .\build_theme_to_sw_l2_correlation.py --ts-code 代码.SZ --source fund --output .\reports\theme_watch\correlations\theme_代码_to_sw_l2_correlation.csv
```

如果返回 0 行：
- 不硬替代。
- 先核对代码是否写错。
- 只有用户确认后，才用相近代码替换。

### 第二步：判断映射质量

看相关性表前 5 名：
- `>= 0.90`：高度纯映射，可以作为主观察对象。
- `0.70 - 0.90`：可用映射，但需要看是否分散到多个行业。
- `< 0.50`：低相关异常，先做校验页，不纳入正式主题组。

### 第三步：生成专题图形页

如果是独立主题：

```powershell
py .\build_sw_l2_topic_report.py --codes 申万代码1 申万代码2 申万代码3 --title "主题名 - 申万二级关联观察" --output .\reports\theme_watch\pages\theme_xxx_sw_l2_watch_report.html
```

如果是对照或异常：
- 文件名使用 `compare` 或 `check`。
- 文档中明确写出异常原因或对照目的。

### 第四步：更新总览和清单

需要同步更新：
- [theme_to_sw_watchlist.md](/D:/CC/Industry%20Insight/reports/theme_watch/theme_to_sw_watchlist.md)
- [theme_watch_dashboard.py](/D:/CC/Industry%20Insight/theme_watch_dashboard.py)

更新后重新生成入口页：

```powershell
py .\theme_watch_dashboard.py
```

## 4. 合并规则

可以合并：
- 两个 ETF 的前 5 个申万二级高度重叠。
- 核心申万二级相同，差异只是宽基/窄基。
- 行业归属一致，且用户观察目的相同。

不建议合并：
- 只是风格相近，但申万二级结构不同。
- 只是走势相关，但申万一级不同。
- 相关性来自行情扩散，而不是行业归属。

已合并案例：
- `159928 消费 ETF` + `512690 酒 ETF` → 消费酒主题组
- `512010 医药 ETF` + `512170 医疗 ETF` → 医药医疗主题组
- `515230 软件 ETF` + `159998 计算机 ETF` → 软件计算机主题组

已拆分案例：
- `512880 证券 ETF` 中的软件/计算机对象拆出，证券页只保留非银金融。
- `159870 化工 ETF` 从周期资源组拆出，单独作为基础化工对照。

## 5. 页面分类

### 正式主题页

用于日常观察。文件名一般是：
- `theme_xxx_sw_l2_watch_report.html`
- `theme_group_name_sw_l2_watch_report.html`

### 对照页

用于观察相邻但不应混入核心主题的对象。文件名一般包含：
- `compare`
- `对照`

### 校验页

用于相关性异常或数据口径待确认。文件名一般包含：
- `check`
- `低相关校验`

## 6. 当前重点提醒

- `512200 房地产 ETF` 与申万房地产相关性偏低，暂时是校验对象。
- `半导体`、`光伏`、`电网设备` 等多为趋势延续型，需要防止把“已经涨很久”误判为“刚启动”。
- `白酒`、`医药医疗`、`证券` 等目前多为未启动或低位观察，需要重点看是否出现年线收敛、贴近和越过。
- `拥挤偏高` 或 `过热预警` 只作为辅助风险层，不单独决定启动。

## 7. 输出文件留痕原则

原始相关性 CSV 不删除，作为映射依据。

单 ETF 旧专题页在合并后可以保留为留痕，但总览页只链接正式合并后的主题页。

如果后续文件过多，再统一迁移到：
- `reports/theme_watch/`
- `reports/theme_watch/archive/`

当前阶段采用复制归档：新入口使用 `reports/theme_watch/`，根目录旧文件作为临时留痕，确认无误后再统一删除。

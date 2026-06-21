# Industry Insight

本项目用于把关注中的 ETF / 主题指数映射到申万二级行业，并用 Tushare 数据生成行业启动观察页。

## 主要入口

- 总览页：[reports/theme_watch/index.html](/D:/CC/Industry%20Insight/reports/theme_watch/index.html)
- 主题清单：[reports/theme_watch/theme_to_sw_watchlist.md](/D:/CC/Industry%20Insight/reports/theme_watch/theme_to_sw_watchlist.md)
- 主题观察 SOP：[reports/theme_watch/theme_watch_sop.md](/D:/CC/Industry%20Insight/reports/theme_watch/theme_watch_sop.md)
- 每日更新 runbook：[reports/theme_watch/daily_update_runbook.md](/D:/CC/Industry%20Insight/reports/theme_watch/daily_update_runbook.md)

## 核心脚本

- `daily_update_theme_watch.py`：每日收盘后更新数据、扫描、相关性、专题页和总览页。
- `theme_watch_config.py`：集中维护 ETF / 主题指数、相关性输出和专题页配置。
- `build_theme_to_sw_l2_correlation.py`：计算 ETF / 主题指数与申万二级行业的日收益相关性。
- `build_sw_l2_topic_report.py`：按申万二级代码生成专题图形页。
- `theme_watch_dashboard.py`：生成 ETF 优先的主题观察总览页。

## 指标口径

- 主指标主要描述中长期结构，例如年线位置、低位收敛、突破行为和龙头确认。
- 辅助指标主要描述短期状态与风险，例如吸筹率分位、波动率异常、拥挤度和映射质量。
- 主/辅分类不按一阶或二阶函数机械划分，而按指标在策略里的作用划分。
- 均值回归思想只用于标准化偏离和风险修正，不直接套用配置模型权重。
- 详细规则见 [indicator_hierarchy_v1.md](/D:/CC/Industry%20Insight/indicator_hierarchy_v1.md)。

## 常用命令

每日正常更新：

```powershell
cd "D:\CC\Industry Insight"
py .\daily_update_theme_watch.py
```

只重建页面，不抓取数据、不重新扫描：

```powershell
py .\daily_update_theme_watch.py --skip-fetch --skip-scan --skip-correlations --allow-non-trade-day
```

检查流程但不执行：

```powershell
py .\daily_update_theme_watch.py --dry-run
```

## 文件组织

- `reports/theme_watch/` 是正式输出区。
- 根目录下被 `.gitignore` 忽略的旧 `theme_*.html`、`theme_*_to_sw_l2_correlation.csv` 和旧清单/SOP 是历史留痕，不作为当前入口。
- `.cache_scan_v2/` 是本地数据缓存，不纳入 Git。

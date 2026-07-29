# Agent Bootstrap

AI agents must read [AI_PROJECT_SOP.md](AI_PROJECT_SOP.md) first before reading other project files or modifying this repository.

## Task routing

- ETF、指数、核心成分、行业启动、Vercel或`etf-watch-data`任务：随后完整读取
  `industry_insight_sandbox/ETF_CONSTITUENT_WATCH_MACHINE_SOP.md`。
- 涉及513970、513230、017832或港股QDII：再完整读取
  `industry_insight_sandbox/HK_QDII_WATCH_MACHINE_SOP.md`。
- 传统申万二级扫描、GitHub Pages或`reports/theme_watch/`任务：读取
  `reports/theme_watch/theme_watch_sop.md`及对应runbook。

## Durable rules

- 当前ETF生产版本为`ETF Watch v2.1.0`，统一总览必须包含22个标的。
- 20个核心专题与2个港股专题使用不同计算引擎，只在编排、总览、校验和发布层合并。
- 生产发布只允许从`main`执行；不得绕过日期不回退、并发、测试或Vercel前置保护。
- 不得把`.cache_scan_v2`、`reports/theme_watch/`或申万二级标签引入ETF核心成分策略。
- 保留用户已有的未提交变更；提交前只暂存与当前任务直接相关的文件。

## Required verification

ETF生产变更至少运行：

```powershell
cd industry_insight_sandbox
python -m unittest discover -s tests -p "test_*.py"
npm run lint
npm test
npm run build:vercel
```

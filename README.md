# Theme Watch

行业主题观察与ETF核心成分启动监控仓库。

当前正式版本：`ETF Watch v2.1.0`

## 当前生产系统

### ETF与指数核心成分观察

这是当前自动运行的主要生产链路：

- 统一观察22个标的：20个A股ETF/指数专题、2个港股消费QDII专题
- 三层策略：低位收敛、带量突破年线、权重龙头确认
- 工作日北京时间22:25启动，数据不完整时在同一任务内最多重试3次，每次间隔10分钟
- 只允许`main`分支发布生产数据
- Vercel构建和部署成功后，才更新`etf-watch-data`数据分支
- 生产站点：[ETF核心成分观察](https://etf-core-constituent-watch.vercel.app)

主要入口：

- `run_etf_constituent_workflow.py`
- `.github/workflows/etf-constituent-daily.yml`
- `industry_insight_sandbox/README.md`
- `industry_insight_sandbox/ETF_CONSTITUENT_WATCH_MACHINE_SOP.md`
- `industry_insight_sandbox/HK_QDII_WATCH_MACHINE_SOP.md`

本地运行：

```powershell
python -m pip install -r requirements-etf-constituent.txt
python run_etf_constituent_workflow.py --end-date YYYYMMDD --trigger-type manual
cd industry_insight_sandbox
npm ci
npm test
npm run lint
npm run build:vercel
```

### 传统Theme Watch报告

传统申万二级扫描、静态报告和GitHub Pages仍保留，但
`.github/workflows/theme-watch-daily.yml`当前只支持手动触发，不再定时运行。

主要入口：

- `run_theme_watch_workflow.py`
- `.github/workflows/theme-watch-daily.yml`
- `reports/theme_watch/theme_watch_sop.md`
- `reports/theme_watch/daily_update_runbook.md`

## 数据与发布边界

- ETF生产数据：`industry_insight_sandbox/data/`
- ETF实时数据分支：`etf-watch-data`
- 传统报告：`reports/theme_watch/`
- 传统扫描缓存：`.cache_scan_v2/`
- 两条策略链路不得混用缓存、标签或成分选择逻辑

## GitHub Secrets

ETF生产链路需要：

- `TUSHARE_TOKEN`
- `VERCEL_TOKEN`
- `VERCEL_ORG_ID`
- `VERCEL_PROJECT_ID`
- `Theme_Watch_FEISHU_WEBHOOK_URL`
- `Theme_Watch_FEISHU_WEBHOOK_SECRET`

任何密钥值都不得写入Git、日志、测试快照或构建产物。

## AI接手顺序

AI代理必须先读取：

1. `AI_PROJECT_SOP.md`
2. 与任务对应的机器SOP
3. 相关README、测试和工作流

具体规则见`AGENTS.md`。

# Daily Close Update Runbook

Run this after the market data is likely available, preferably after 20:00 China time:

```powershell
cd "D:\CC\Industry Insight"
py .\run_theme_watch_workflow.py --trigger-type manual
```

The updater now skips non-trading days by default. If you intentionally want to rebuild on a non-trading day, add:

```powershell
py .\run_theme_watch_workflow.py --trigger-type manual --allow-non-trade-day
```

The workflow does five things:
- updates the recent `sw_daily` master history and whole-market daily amount cache;
- reruns the SW L2 strategy scan using the master history cache;
- refreshes the ETF/index-to-SW-L2 correlation CSVs;
- rebuilds all official theme pages and the dashboard under `reports/theme_watch/`.
- verifies that generated reports exist and that correlation data covers the run date.

If Tushare has not published the latest close yet, rerun the same command later.

To test the workflow without network calls or file generation:

```powershell
py .\run_theme_watch_workflow.py --trigger-type manual --dry-run
```

For a specific trade date:

```powershell
py .\run_theme_watch_workflow.py --trigger-type manual --end-date 20260616
```

Useful partial runs:

```powershell
py .\daily_update_theme_watch.py --skip-fetch
py .\daily_update_theme_watch.py --skip-correlations
py .\daily_update_theme_watch.py --skip-pages
```

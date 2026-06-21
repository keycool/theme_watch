# Daily Close Update Runbook

Run this after the market data is likely available, preferably after 18:30 China time:

```powershell
cd "D:\CC\Industry Insight"
py .\daily_update_theme_watch.py
```

The updater now skips non-trading days by default. If you intentionally want to rebuild on a non-trading day, add:

```powershell
py .\daily_update_theme_watch.py --allow-non-trade-day
```

The updater does four things:
- updates the recent `sw_daily` master history and whole-market daily amount cache;
- reruns the SW L2 strategy scan using the master history cache;
- refreshes the ETF/index-to-SW-L2 correlation CSVs;
- rebuilds all official theme pages and the dashboard under `reports/theme_watch/`.

If Tushare has not published the latest close yet, rerun the same command later.

To test the workflow without network calls or file generation:

```powershell
py .\daily_update_theme_watch.py --dry-run
```

For a specific trade date:

```powershell
py .\daily_update_theme_watch.py --end-date 20260616
```

Useful partial runs:

```powershell
py .\daily_update_theme_watch.py --skip-fetch
py .\daily_update_theme_watch.py --skip-correlations
py .\daily_update_theme_watch.py --skip-pages
```

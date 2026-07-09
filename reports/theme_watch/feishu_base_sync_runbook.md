# Feishu Base Sync Runbook

## Purpose

This runbook covers the first sync layer for pushing theme-watch results into Feishu Base.

Current scope:

- sync one `workflow_runs` row;
- sync `industry_scan_daily` snapshot rows from `sw_l2_strategy_scan.csv`;
- no correlation-table sync yet;
- no publish-table sync yet.

Script entry:

[`/D:/CC/Industry Insight/theme_watch_base_sync.py`](/D:/CC/Industry%20Insight/theme_watch_base_sync.py)

## Required Base Tables

Create these tables first:

1. `workflow_runs`
2. `industry_scan_daily`

Recommended schema source:

[`/D:/CC/Industry Insight/reports/theme_watch/feishu_base_schema_design.md`](/D:/CC/Industry%20Insight/reports/theme_watch/feishu_base_schema_design.md)

## Required Environment Variables

Recommended variables:

```powershell
$env:THEME_WATCH_BASE_TOKEN = "<base_token>"
$env:THEME_WATCH_RUNS_TABLE = "workflow_runs"
$env:THEME_WATCH_SCAN_TABLE = "industry_scan_daily"
$env:THEME_WATCH_BASE_IDENTITY = "user"
```

Notes:

- `THEME_WATCH_BASE_TOKEN` is required for real writes.
- table values can be table names in V1.
- `THEME_WATCH_BASE_IDENTITY` defaults to `user`.

## Dry Run

Use dry-run first. It does not write to Base.

```powershell
cd "D:\CC\Industry Insight"
py -B .\theme_watch_base_sync.py `
  --run-id dryrun-001 `
  --dry-run `
  --scan-csv .\sw_l2_strategy_scan.csv `
  --status success `
  --trigger-type manual `
  --end-date 20260708 `
  --is-trade-day
```

Expected behavior:

- prints one `workflow_runs` payload;
- prints one `industry_scan_daily` payload per scan row.

## Real Write

After Base tables exist and dry-run looks correct:

```powershell
cd "D:\CC\Industry Insight"
py -B .\theme_watch_base_sync.py `
  --run-id gha-20260708-2000 `
  --scan-csv .\sw_l2_strategy_scan.csv `
  --status success `
  --trigger-type schedule `
  --end-date 20260708 `
  --started-at 2026-07-08T20:00:00+08:00 `
  --finished-at 2026-07-08T20:08:30+08:00 `
  --is-trade-day
```

## Optional Arguments

Useful flags:

- `--issues-count 1`
- `--issues-summary "Tushare stale on scan date"`
- `--stdout-file <path>`
- `--artifact-url <url>`
- `--pages-url <url>`
- `--skip-run`
- `--skip-scan`

## Data Sources Used By The Script

The script reads:

- [`/D:/CC/Industry Insight/sw_l2_strategy_scan.csv`](/D:/CC/Industry%20Insight/sw_l2_strategy_scan.csv)
- [`/D:/CC/Industry Insight/.cache_scan_v2/sw_daily_full_history.csv`](/D:/CC/Industry%20Insight/.cache_scan_v2/sw_daily_full_history.csv)
- [`/D:/CC/Industry Insight/theme_watch_config.py`](/D:/CC/Industry%20Insight/theme_watch_config.py)

It derives:

- `scan_latest_date`
- `scan_rows`
- `page_file_count`
- `correlation_file_count`
- `sw_daily_master_max_date`

## Current Idempotency Strategy

The script uses logical business keys and tries to update existing Base rows before creating new ones:

- `workflow_runs.run_id`
- `industry_scan_daily.snapshot_key`

This is good enough for first-pass retry safety.

## Known Limitations

1. `theme_correlation_daily` sync is not implemented yet.
2. `report_publish_daily` sync is not implemented yet.
3. First version assumes Base field names exactly match the schema document.
4. If Base-side text encodings or select options differ from the schema, writes may fail.

## Recommended Next Step

After the two Base tables are created and this script is verified:

1. connect it to GitHub Actions after daily update completes;
2. add `theme_correlation_daily` sync;
3. add `report_publish_daily` sync.

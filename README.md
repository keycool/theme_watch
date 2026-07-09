# Theme Watch

This repository is the dedicated production workflow for the industry theme watch system.

It is responsible for:

- running the daily Tushare-backed update
- refreshing the SW L2 scan
- rebuilding `reports/theme_watch/`
- publishing the report via GitHub Pages
- syncing workflow state to Feishu Base

## Main Entry Points

- `daily_update_theme_watch.py`
- `run_theme_watch_workflow.py`
- `.github/workflows/theme-watch-daily.yml`

## Report Output

Main report:

- `reports/theme_watch/index.html`

Supporting output:

- `reports/theme_watch/pages/`
- `reports/theme_watch/correlations/`

## GitHub Actions

The repository is designed to run on GitHub Actions on weekdays at `20:00` China time.

The workflow:

1. restores `.cache_scan_v2` from Actions cache
2. runs the daily update workflow
3. uploads workflow logs
4. uploads the static report artifact
5. deploys `reports/theme_watch/` to GitHub Pages
6. syncs run state to Feishu Base when Feishu secrets are configured

## Required Secrets

Minimum:

- `TUSHARE_TOKEN`

For Feishu sync:

- `THEME_WATCH_BASE_TOKEN`
- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`

## Related Docs

- `reports/theme_watch/daily_update_runbook.md`
- `reports/theme_watch/github_actions_workflow_runbook.md`
- `reports/theme_watch/github_actions_setup_checklist.md`
- `reports/theme_watch/feishu_base_sync_runbook.md`

## Local Dry Run

```powershell
python run_theme_watch_workflow.py --dry-run --skip-sync
```

## Scope

This repository is intentionally focused on the production workflow only.

It does not try to be:

- a generic Tushare research toolbox
- an experiment archive
- a notebook-heavy analysis sandbox

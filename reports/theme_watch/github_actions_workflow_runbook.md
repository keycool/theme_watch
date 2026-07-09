# GitHub Actions Workflow Runbook

## What This Adds

The repository can run the theme watch daily update in GitHub Actions at **20:00 China time** on weekdays.

Workflow file:
- [theme-watch-daily.yml](/D:/CC/Industry%20Insight/.github/workflows/theme-watch-daily.yml)

Wrapper entrypoint:
- [run_theme_watch_workflow.py](/D:/CC/Industry%20Insight/run_theme_watch_workflow.py)

Setup checklist:
- [github_actions_setup_checklist.md](/D:/CC/Industry%20Insight/reports/theme_watch/github_actions_setup_checklist.md)

Repo migration plan:
- [repo_migration_plan.md](/D:/CC/Industry%20Insight/reports/theme_watch/repo_migration_plan.md)

## Required GitHub Secrets

Add these repository secrets before enabling the schedule:

- `TUSHARE_TOKEN`
- `THEME_WATCH_BASE_TOKEN`
- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`

Recommended split:

- Required for update only: `TUSHARE_TOKEN`
- Required for Feishu sync: `THEME_WATCH_BASE_TOKEN`, `FEISHU_APP_ID`, `FEISHU_APP_SECRET`

If the three Feishu secrets are not complete, the workflow now automatically runs with `--skip-sync`.

## Feishu Setup

The workflow is configured to sync Base data with `--as bot`, not `--as user`.

That means the Feishu app behind `FEISHU_APP_ID` / `FEISHU_APP_SECRET` must:

1. Have Base read/write scopes enabled.
2. Be allowed to access the target Base.
3. Be able to write to:
   - Base `PNtUbSB1GaweCFsZQ1cc6Kdzn1f`
   - Table `tblyVEBVpnLy50k4` (`workflow_runs`)
   - Table `tblp78QebGDZbot7` (`industry_scan_daily`)

If bot writes fail with permission errors, first check app scope and Base sharing before changing code.

Practical setup order:

1. Open the Feishu developer console for the app matching `FEISHU_APP_ID`.
2. Enable the Base scopes needed for table read/write.
3. In the target Base, add or authorize that app so the bot can access the Base.
4. Confirm the bot can read fields and write records for:
   - `tblyVEBVpnLy50k4`
   - `tblp78QebGDZbot7`

Minimum command path used by this project:

- `lark-cli base +field-list`
- `lark-cli base +record-search`
- `lark-cli base +record-upsert`

## Workflow Behavior

The workflow does four things:

1. Restores `.cache_scan_v2` from GitHub Actions cache.
2. Runs the daily updater.
3. Runs a local self-check and writes a JSON summary under `logs/theme_watch_workflow/`.
4. Syncs run status and scan rows to Feishu Base when Base credentials are present.

## Notes About Cache

This workflow still depends on `.cache_scan_v2`.

That is important because the current scan logic needs historical cached data, and the updater only fetches a limited new chunk each run. Without restoring prior cache, a brand-new runner is unlikely to produce stable scan output.

## First Validation

Use manual dispatch first.

Recommended first run:

```text
end_date: leave blank
allow_non_trade_day: false
```

Recommended validation sequence:

1. First run with only `TUSHARE_TOKEN` configured, to validate cloud update + cache + artifact generation.
2. Then add the three Feishu secrets and rerun `workflow_dispatch`.
3. Only after both manual runs succeed, leave the weekday 20:00 schedule enabled.

After the first cloud run, verify:

- Actions log contains `status=success` or `status=warning`
- `logs/theme_watch_workflow/*.json` was uploaded
- GitHub Pages artifact contains `reports/theme_watch/index.html`

After the first Feishu-enabled run, additionally verify:

- Feishu `workflow_runs` has a new row
- Feishu `industry_scan_daily` has one row per `snapshot_key`
- No permission error appears in the Base sync step

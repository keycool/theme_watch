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
- `Theme_Watch_FEISHU_WEBHOOK_URL`
- `Theme_Watch_FEISHU_WEBHOOK_SECRET`

Current split:

- Required for update and deploy: `TUSHARE_TOKEN`
- Required for Feishu notification: `Theme_Watch_FEISHU_WEBHOOK_URL`
- Optional when webhook signature is enabled: `Theme_Watch_FEISHU_WEBHOOK_SECRET`

The webhook keyword is fixed in workflow as `theme_watch`.

## Feishu Setup

The workflow no longer writes to Feishu Base.

The current notification path is:

1. GitHub Actions runs the update job.
2. The workflow uploads `logs/theme_watch_workflow/` as artifact.
3. The notify job downloads the artifact.
4. `theme_watch_feishu_webhook.py` reads the latest summary JSON and sends a text message to the Feishu webhook robot.

Webhook-side settings expected by this project:

1. Custom keyword enabled with value `theme_watch`.
2. Signature check enabled only if `Theme_Watch_FEISHU_WEBHOOK_SECRET` is configured.
3. IP allowlist disabled unless you want to maintain GitHub Actions egress IP ranges yourself.

## Workflow Behavior

The workflow does four things:

1. Restores `.cache_scan_v2` from GitHub Actions cache.
2. Runs the daily updater wrapper and writes a JSON summary under `logs/theme_watch_workflow/`.
3. Deploys `reports/theme_watch/` to GitHub Pages and verifies the published homepage and topic pages.
4. Sends the latest workflow summary to the Feishu webhook robot.

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
2. Then add the webhook secret(s) and rerun `workflow_dispatch`.
3. Only after both manual runs succeed, leave the weekday 20:00 schedule enabled.

After the first cloud run, verify:

- Actions log contains `status=success` or `status=warning`
- `logs/theme_watch_workflow/*.json` was uploaded
- GitHub Pages artifact contains `reports/theme_watch/index.html`

After the first Feishu-enabled run, additionally verify:

- The `notify` job completes
- Feishu group receives one text message
- The message includes `status`, `issues_count`, `pages`, and `github_actions`

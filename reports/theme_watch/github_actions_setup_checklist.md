# GitHub Actions Setup Checklist

This is the practical setup sheet for turning on the cloud workflow.

Related files:

- [theme-watch-daily.yml](/D:/CC/Industry%20Insight/.github/workflows/theme-watch-daily.yml)
- [github_actions_workflow_runbook.md](/D:/CC/Industry%20Insight/reports/theme_watch/github_actions_workflow_runbook.md)
- [run_theme_watch_workflow.py](/D:/CC/Industry%20Insight/run_theme_watch_workflow.py)

## 1. GitHub Repository Secrets

Add these in:

`GitHub repo -> Settings -> Secrets and variables -> Actions -> New repository secret`

### Required For Cloud Update

1. `TUSHARE_TOKEN`
   Value source:
   - your existing local Tushare token
   - or the token currently used by this project on your machine

### Required For Feishu Base Sync

1. `THEME_WATCH_BASE_TOKEN`
   Value:
   - `PNtUbSB1GaweCFsZQ1cc6Kdzn1f`

2. `FEISHU_APP_ID`
   Value source:
   - the App ID of the Feishu app you want GitHub Actions to use as bot identity

3. `FEISHU_APP_SECRET`
   Value source:
   - the matching App Secret of that same Feishu app

## 2. Values Already Fixed In Code

These do not need to be configured as GitHub secrets right now because they are already in the workflow file:

- Base ID: `PNtUbSB1GaweCFsZQ1cc6Kdzn1f`
- `workflow_runs` table ID: `tblyVEBVpnLy50k4`
- `industry_scan_daily` table ID: `tblp78QebGDZbot7`
- Feishu identity mode: `bot`
- Schedule: weekdays `20:00` China time

## 3. Feishu App Requirements

Use one Feishu app for this workflow end to end.

Open:

`Feishu developer console -> your app`

Then check these three areas.

### A. App Credentials

Make sure you can see:

- App ID
- App Secret

These become:

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`

### B. Permissions / Scopes

The workflow needs Base capabilities that cover this command path:

- `lark-cli base +field-list`
- `lark-cli base +record-search`
- `lark-cli base +record-upsert`

So in the Feishu console, enable the Base / 多维表格 permissions that cover:

1. Reading table structure / fields
2. Reading records
3. Creating records
4. Updating records

Practical rule:

- if you see separate Base permissions for field read and record read/write, enable all of them
- if the console groups them differently, choose the set that clearly covers field read plus record read/write

Do not spend time over-optimizing the first permission set. The fastest path is:

1. enable the obvious Base read/write permissions
2. run one manual workflow
3. if Feishu returns a missing-scope error, add exactly that missing scope

### C. Resource Access

The app also needs access to the actual Base resource, not just API permissions.

In the target Base, confirm the app is allowed to access:

- Base `PNtUbSB1GaweCFsZQ1cc6Kdzn1f`
- Table `tblyVEBVpnLy50k4`
- Table `tblp78QebGDZbot7`

If the app has scopes but still gets permission denied, this resource authorization is the first place to check.

## 4. Recommended Activation Order

### Phase 1: Cloud Update Only

Configure only:

- `TUSHARE_TOKEN`

Then run `workflow_dispatch` once.

Expected result:

- updater runs
- cache restores or initializes
- report artifact uploads
- Pages artifact uploads
- workflow log JSON uploads
- Base sync is skipped automatically

### Phase 2: Feishu Sync

Add:

- `THEME_WATCH_BASE_TOKEN`
- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`

Then run `workflow_dispatch` again.

Expected result:

- everything from Phase 1 still works
- `workflow_runs` gets a new row
- `industry_scan_daily` gets one row per `snapshot_key`

## 5. First Manual Run Checklist

Open:

`GitHub repo -> Actions -> Theme Watch Daily Update -> Run workflow`

Use:

- `end_date`: blank
- `allow_non_trade_day`: `false`

Check after run:

1. Actions log includes `run_id=...`
2. Actions log includes `status=success` or `status=warning`
3. Artifact `theme-watch-workflow-logs` exists
4. Artifact contains one JSON summary and one stdout log
5. If Feishu secrets were configured, Base sync step has no permission error

## 6. What To Check If Feishu Sync Fails

Check in this order:

1. `FEISHU_APP_ID` and `FEISHU_APP_SECRET` belong to the same app
2. the app has Base read/write related permissions enabled
3. the app can access the target Base resource
4. the table IDs are still:
   - `tblyVEBVpnLy50k4`
   - `tblp78QebGDZbot7`
5. the Base token is still:
   - `PNtUbSB1GaweCFsZQ1cc6Kdzn1f`

If the error explicitly says a scope is missing, use that exact missing scope as the next adjustment.

## 7. Current Assumption

This setup assumes:

- GitHub Actions is only the scheduler and cloud runner
- `.cache_scan_v2` remains the short-term history source
- Feishu Base is the workflow state store, not the full market history store

That is the right first migration step because it minimizes changes to the scan logic.

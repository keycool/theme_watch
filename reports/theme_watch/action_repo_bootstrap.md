# Action Repo Bootstrap

This is the minimum set required to start the dedicated GitHub Actions repository immediately.

Target repo:

- `keycool/theme_watch`

## 1. Repository Must-Have Files

Create these first:

- `.github/workflows/theme-watch-daily.yml`
- `.gitignore`
- `README.md`
- `requirements-theme-watch.txt`

Then copy these business files:

- `daily_update_theme_watch.py`
- `run_theme_watch_workflow.py`
- `theme_watch_base_sync.py`
- `theme_watch_config.py`
- `theme_watch_dashboard.py`
- `build_theme_to_sw_l2_correlation.py`
- `build_sw_l2_topic_report.py`
- `build_sw_l2_visual_report.py`
- `build_sw_l2_sample_pool.py`
- `build_sw_l2_focus_leaderboard.py`
- `run_sw_l2_strategy_scan.py`
- `strategy_scan_common.py`
- `industry_start_strategy_v1_engine.py`
- `backfill_sw_daily_history.py`
- `backfill_daily_market_history.py`
- `sw_data_utils.py`

## 2. Report Baseline Files

Copy these so the repo has a usable initial report tree:

- `reports/theme_watch/index.html`
- `reports/theme_watch/correlations/`
- `reports/theme_watch/pages/`

Also copy:

- `sw_l2_strategy_scan.csv`
- `sw_l2_strategy_scan_summary.md`
- `sw_l2_strategy_leaderboard.md`

## 3. Docs To Carry Over

- `reports/theme_watch/daily_update_runbook.md`
- `reports/theme_watch/theme_watch_sop.md`
- `reports/theme_watch/theme_to_sw_watchlist.md`
- `reports/theme_watch/feishu_base_schema_design.md`
- `reports/theme_watch/feishu_base_sync_runbook.md`
- `reports/theme_watch/github_actions_workflow_runbook.md`
- `reports/theme_watch/github_actions_setup_checklist.md`
- `reports/theme_watch/repo_migration_plan.md`
- `reports/theme_watch/action_repo_bootstrap.md`

## 4. GitHub Secrets

Create these in the new repository:

### Required

- `TUSHARE_TOKEN`

### Required For Feishu Sync

- `THEME_WATCH_BASE_TOKEN`
- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`

## 5. Feishu Fixed IDs

Use these exact values:

- Base token: `PNtUbSB1GaweCFsZQ1cc6Kdzn1f`
- `workflow_runs`: `tblyVEBVpnLy50k4`
- `industry_scan_daily`: `tblp78QebGDZbot7`

## 6. Workflow Must-Have Behavior

The workflow must do all of the following:

1. run on weekday schedule at `20:00` China time
2. support manual `workflow_dispatch`
3. install Python
4. install Node
5. install `lark-cli`
6. restore `.cache_scan_v2` from Actions cache
7. run `run_theme_watch_workflow.py`
8. upload `logs/theme_watch_workflow/`
9. upload `reports/theme_watch/` as artifact
10. deploy `reports/theme_watch/` to GitHub Pages
11. save `.cache_scan_v2` back to cache

## 7. .gitignore Must-Have

At minimum ignore:

- `.cache/`
- `.cache_scan_v2/`
- `__pycache__/`
- `logs/theme_watch_workflow/`
- `*.pyc`
- `*.log`

## 8. First Validation Sequence

### Run 1

Configure only:

- `TUSHARE_TOKEN`

Then run:

- `workflow_dispatch`

Goal:

- validate update flow
- validate cache
- validate report artifact
- validate Pages artifact

### Run 2

Add:

- `THEME_WATCH_BASE_TOKEN`
- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`

Then run:

- `workflow_dispatch`

Goal:

- validate `workflow_runs` sync
- validate `industry_scan_daily` sync

## 9. Do Not Bring In First Batch

Do not copy:

- `archive/`
- `.cache/`
- `.cache_scan_v2/`
- `logs/`
- `generated_strategy_inputs/`
- `generated_strategy_inputs_l2/`
- unrelated probe and experiment files

## 10. Fastest Practical Order

1. create empty repo structure
2. copy must-have code
3. copy workflow file
4. copy report baseline
5. push first commit
6. add `TUSHARE_TOKEN`
7. run first manual action
8. add Feishu secrets
9. run second manual action
10. leave weekday 20:00 schedule enabled

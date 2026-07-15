# Theme Watch Repo Migration Plan

This is the migration whitelist for the new dedicated GitHub repository:

- target repo: `keycool/theme_watch`
- target purpose: cloud execution, report generation, GitHub Actions scheduling, Feishu Base sync

## Migration Rule

Only move files that are directly required to:

1. fetch data
2. update cache
3. run the SW L2 scan
4. rebuild `reports/theme_watch/`
5. run GitHub Actions
6. sync workflow state to Feishu Base

Do not move general experiments, unrelated AI tooling, or historical archive content into the first production repo version.

## A. Must Include

These should go into the new repository in the first migration batch.

### Core Python Entry Points

- `daily_update_theme_watch.py`
- `run_theme_watch_workflow.py`
- `theme_watch_base_sync.py`

### Core Business Modules

- `theme_watch_config.py`
- `theme_watch_dashboard.py`
- `build_theme_to_sw_l2_correlation.py`
- `build_sw_l2_topic_report.py`
- `build_sw_l2_visual_report.py`
- `run_sw_l2_strategy_scan.py`
- `strategy_scan_common.py`
- `industry_start_strategy_v1_engine.py`
- `build_sw_l2_sample_pool.py`
- `build_sw_l2_focus_leaderboard.py`

### Data Fetch / Cache Modules

- `backfill_sw_daily_history.py`
- `backfill_daily_market_history.py`
- `sw_data_utils.py`

### Workflow / Dependency Files

- `.github/workflows/theme-watch-daily.yml`
- `requirements-theme-watch.txt`
- `.gitignore`
- `README.md`

### Business Documentation

- `reports/theme_watch/daily_update_runbook.md`
- `reports/theme_watch/theme_watch_sop.md`
- `reports/theme_watch/theme_to_sw_watchlist.md`
- `reports/theme_watch/feishu_base_schema_design.md`
- `reports/theme_watch/feishu_base_sync_runbook.md`
- `reports/theme_watch/github_actions_workflow_runbook.md`
- `reports/theme_watch/github_actions_setup_checklist.md`
- `reports/theme_watch/repo_migration_plan.md`

## B. Include As Initial Runtime Data

These are not code, but should be carried into the new repo because the current workflow expects them or benefits from them.

### Current Static Report Output

- `reports/theme_watch/index.html`
- `reports/theme_watch/correlations/`
- `reports/theme_watch/pages/`

Reason:

- this gives the new repo an immediately usable Pages artifact baseline
- it avoids starting from an empty report tree

### Current Scan Output Snapshot

- `sw_l2_strategy_scan.csv`
- `sw_l2_strategy_scan_summary.md`
- `sw_l2_strategy_leaderboard.md`

Reason:

- useful for first comparison and dry-run validation
- not strictly required forever, but useful for first repo bring-up

## C. Keep Out Of The First Migration

These should stay in the current workspace for now.

### Historical / Archive Content

- `archive/`
- `reports/theme_watch/archive/`

### Unrelated Generated Data

- `generated_strategy_inputs/`
- `generated_strategy_inputs_l2/`
- `erp_signal.json`
- `relative_signal.json`

### Local Runtime Cache

- `.cache/`
- `.cache_scan_v2/`
- `__pycache__/`
- `logs/`

Reason:

- these are environment-specific runtime artifacts
- `.cache_scan_v2/` should be initialized locally, then persisted by GitHub Actions cache rather than committed

### Unrelated Utility / Probe Files

- `tushare_capability_probe.py`
- `tushare_capability_report.json`
- `tushare_article_mapping.md`
- `check_sw_backfill_status.py`
- `run_one_sw_backfill.cmd`
- `run_one_sw_backfill.ps1`

### Strategy Notes Not Needed For Runtime

- `indicator_hierarchy_v1.md`
- `industry_crowding_filter_v1.md`
- `industry_crowding_filter_v1_field_mapping.md`
- `industry_start_l2_sop.md`
- `industry_start_strategy_v1.md`
- `industry_start_strategy_v1_field_mapping.md`
- `sw_l2_crowding_observation_notes.md`
- `sw_l2_threshold_comparison.md`

These can be added later if you want the new repo to also act as a research knowledge base, but they are not required for first deployment.

## D. Recommended New Repo Structure

Keep the first version flat and close to the current working code to reduce migration risk.

```text
theme_watch/
├── .github/
│   └── workflows/
│       └── theme-watch-daily.yml
├── reports/
│   └── theme_watch/
│       ├── correlations/
│       ├── pages/
│       ├── index.html
│       ├── daily_update_runbook.md
│       ├── theme_watch_sop.md
│       ├── theme_to_sw_watchlist.md
│       ├── feishu_base_schema_design.md
│       ├── feishu_base_sync_runbook.md
│       ├── github_actions_workflow_runbook.md
│       ├── github_actions_setup_checklist.md
│       └── repo_migration_plan.md
├── daily_update_theme_watch.py
├── run_theme_watch_workflow.py
├── theme_watch_base_sync.py
├── theme_watch_config.py
├── theme_watch_dashboard.py
├── build_theme_to_sw_l2_correlation.py
├── build_sw_l2_topic_report.py
├── build_sw_l2_visual_report.py
├── build_sw_l2_sample_pool.py
├── build_sw_l2_focus_leaderboard.py
├── run_sw_l2_strategy_scan.py
├── strategy_scan_common.py
├── industry_start_strategy_v1_engine.py
├── backfill_sw_daily_history.py
├── backfill_daily_market_history.py
├── sw_data_utils.py
├── sw_l2_strategy_scan.csv
├── sw_l2_strategy_scan_summary.md
├── sw_l2_strategy_leaderboard.md
├── requirements-theme-watch.txt
├── .gitignore
└── README.md
```

## E. Recommended README Positioning

The new repo README should describe the repo as:

- a scheduled theme watch production workflow
- not a general Tushare research sandbox
- GitHub Actions + GitHub Pages + Feishu Base integrated workflow

## F. Suggested Migration Order

1. Create minimal repo skeleton
2. Copy code whitelist
3. Copy report/output baseline
4. Add workflow files and docs
5. Commit
6. Configure GitHub secrets
7. Run first manual GitHub Actions validation without Feishu sync
8. Enable Feishu sync

## G. First Post-Migration Checks

After files are copied, verify locally in the new repo:

1. `python run_theme_watch_workflow.py --dry-run --skip-sync`
2. `python daily_update_theme_watch.py --dry-run`
3. workflow YAML still points to the correct file names
4. report paths still resolve to `reports/theme_watch/`

## H. Current Assumption

This plan intentionally optimizes for the fastest safe migration.

It does not try to:

- refactor the codebase
- reorganize modules into packages
- redesign the cache model
- convert Feishu sync away from `lark-cli`

Those can be second-phase improvements after the dedicated repo is running.

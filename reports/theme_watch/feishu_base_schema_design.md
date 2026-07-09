# Feishu Base Schema Design For Theme Watch

## Goal

This document defines a Feishu Base schema for the `theme_watch` workflow after moving scheduled execution to GitHub Actions.

The target is not to replace every local cache file with Base records. The target is:

- keep workflow state in a durable cloud system;
- make latest results queryable without opening local CSV files;
- support health checks, freshness checks, and publish tracking;
- avoid storing the full raw `sw_daily` history as Base primary storage.

## Scope

This schema is designed around the current pipeline:

1. refresh recent Tushare history and market cache;
2. run `sw_l2_strategy_scan.csv`;
3. rebuild theme correlation CSVs;
4. rebuild topic pages and dashboard;
5. verify outputs and publish.

Current data scale observed on `2026-07-08`:

- `.cache_scan_v2/sw_daily_full_history.csv`: about `266,034` rows;
- `sw_l2_strategy_scan.csv`: about `88` rows per run;
- `reports/theme_watch/correlations/*.csv`: `20` files per run.

This is why Base should hold state and derived results, while bulk history remains file-based.

## Design Principles

1. Base stores state, snapshots, and publishable results.
2. Files store bulk historical raw data.
3. One workflow run must be traceable end to end.
4. Every result row should point back to a specific `run_id`.
5. Dimension tables should be stable and rarely updated.
6. Fact tables should be append-only by default.

## Recommended Table Set

Recommended first version uses 6 tables:

1. `themes_dim`
2. `topic_pages_dim`
3. `workflow_runs`
4. `industry_scan_daily`
5. `theme_correlation_daily`
6. `report_publish_daily`

Optional later tables:

1. `cache_manifest`
2. `industry_daily_agg`

## 1. `themes_dim`

Purpose:

- registry of tracked ETF/index themes;
- stable metadata for correlation rebuild and homepage grouping.

Recommended unique key:

- `theme_code`

Fields:

| Field | Type | Required | Notes |
|---|---|---:|---|
| `theme_code` | Text | yes | e.g. `512480.SH`, `931994.CSI` |
| `theme_name` | Text | yes | display name |
| `source_type` | Single select | yes | `fund` / `index` / `synthetic` |
| `bucket` | Single select | yes | homepage grouping bucket |
| `default_page_slug` | Text | no | default topic page filename |
| `is_active` | Checkbox | yes | active tracking flag |
| `sort_order` | Number | no | homepage order |
| `notes` | Long text | no | manual notes |

Recommended initial row count:

- `20` active Tushare themes
- optionally `1` synthetic row for `TMT-COMM`

## 2. `topic_pages_dim`

Purpose:

- registry of official topic pages;
- page-to-industry-code mapping source of truth.

Recommended unique key:

- `page_slug`

Fields:

| Field | Type | Required | Notes |
|---|---|---:|---|
| `page_slug` | Text | yes | e.g. `theme_512480_sw_l2_watch_report.html` |
| `page_title` | Text | yes | display title |
| `page_group` | Single select | no | optional category |
| `industry_codes_csv` | Long text | yes | comma-separated SW codes for first version |
| `industry_count` | Formula/Number | no | optional derived count |
| `is_official` | Checkbox | yes | `true` for current official pages |
| `is_active` | Checkbox | yes | soft-delete flag |
| `notes` | Long text | no | migration notes |

Why CSV instead of child rows in v1:

- simpler write path from current Python config;
- enough for homepage retargeting and publish checks;
- can be normalized later if Base-side querying becomes more important.

## 3. `workflow_runs`

Purpose:

- one row per GitHub Actions run;
- top-level health, freshness, and status ledger.

Recommended unique key:

- `run_id`

Fields:

| Field | Type | Required | Notes |
|---|---|---:|---|
| `run_id` | Text | yes | GitHub run id or generated uuid |
| `workflow_name` | Text | yes | e.g. `theme-watch-daily-update` |
| `trigger_type` | Single select | yes | `schedule` / `manual` / `retry` |
| `started_at` | DateTime | yes | run start |
| `finished_at` | DateTime | no | run finish |
| `status` | Single select | yes | `running` / `success` / `failed` / `partial` / `skipped` |
| `end_date` | Text | yes | trade-date target, `YYYYMMDD` |
| `is_trade_day` | Checkbox | yes | result of trade-day guard |
| `sw_daily_master_max_date` | Text | no | from stdout |
| `scan_latest_date` | Text | no | from stdout |
| `scan_rows` | Number | no | from stdout |
| `correlation_file_count` | Number | no | expected 20 |
| `page_file_count` | Number | no | expected official page count |
| `issues_count` | Number | no | number of detected issues |
| `issues_summary` | Long text | no | concise machine-generated summary |
| `artifact_url` | URL | no | workflow artifact or release link |
| `pages_url` | URL | no | GitHub Pages or publish URL |
| `stdout_excerpt` | Long text | no | last useful summary lines |

This table is the main control-plane table.

## 4. `industry_scan_daily`

Purpose:

- store daily scan snapshot rows from `sw_l2_strategy_scan.csv`;
- query latest labels without reading repository files.

Recommended unique key:

- composite logical key: `run_id + industry_code`

Recommended write policy:

- append one full daily snapshot per successful scan run.

Fields:

| Field | Type | Required | Notes |
|---|---|---:|---|
| `run_id` | Link to `workflow_runs` or Text | yes | traceability |
| `trade_date` | Text | yes | from `latest_date` |
| `industry_code` | Text | yes | e.g. `801081.SI` |
| `industry_name` | Text | yes | |
| `l1_name` | Text | yes | |
| `total_mv_yi` | Number | no | |
| `prefilter_label` | Single select | no | |
| `final_label` | Single select | no | |
| `crowding_label` | Single select | no | |
| `summary_line` | Long text | no | |
| `leader_top1_name` | Text | no | |
| `leader_top1_pct_change` | Number | no | percent number as plain numeric value |
| `leader_count` | Number | no | |
| `leader_active_count` | Number | no | |
| `absorption_rate` | Number | no | |
| `absorption_rate_rank_pct` | Number | no | decimal ratio |
| `absorption_rate_5d_change` | Number | no | |
| `close_to_ma60_gap` | Number | no | |
| `ma60_slope_20d` | Number | no | |
| `breakout_emerged` | Checkbox | no | |
| `breakout_confirmed` | Checkbox | no | |
| `local_activity_ok` | Checkbox | no | |
| `has_ma250` | Checkbox | no | |
| `has_amount_ma20` | Checkbox | no | |
| `has_ret_120d_rank` | Checkbox | no | |

Do not put all 51 raw columns into v1 unless needed. The table should be operational, not archival.

If you want exact reproducibility later, keep the full CSV as artifact and only store high-value columns in Base.

## 5. `theme_correlation_daily`

Purpose:

- store daily theme-to-industry ranking results;
- support homepage mapping and drift detection.

Recommended unique key:

- composite logical key: `run_id + theme_code + sw_code`

Recommended write policy:

- append top `N` rows per theme per run;
- recommended `N = 10` in v1.

Reason:

- the full 20 x 124 daily ranking is still manageable, but top10 is usually enough for Base-side operations;
- full ranking can remain in CSV artifacts.

Fields:

| Field | Type | Required | Notes |
|---|---|---:|---|
| `run_id` | Link to `workflow_runs` or Text | yes | |
| `trade_date` | Text | yes | scan/date context |
| `theme_code` | Link to `themes_dim` or Text | yes | |
| `sw_code` | Text | yes | |
| `sw_name` | Text | yes | |
| `l1_name` | Text | no | |
| `rank_no` | Number | yes | 1-based rank |
| `corr_daily_ret` | Number | yes | decimal correlation |
| `common_days` | Number | no | |
| `final_label` | Single select | no | latest scan label copied in |
| `crowding_label` | Single select | no | latest scan label copied in |
| `total_mv_yi` | Number | no | |
| `leader_top1_name` | Text | no | |
| `mapped_page_slug` | Text | no | page selected by current logic |
| `top_in_page_codes` | Checkbox | no | whether correlation top1 is covered by mapped page |

This is the most important table for homepage consistency and semantic drift checks.

## 6. `report_publish_daily`

Purpose:

- one row per generated publishable page or output object;
- separate "data exists" from "page exists".

Recommended unique key:

- composite logical key: `run_id + output_name`

Fields:

| Field | Type | Required | Notes |
|---|---|---:|---|
| `run_id` | Link to `workflow_runs` or Text | yes | |
| `output_type` | Single select | yes | `dashboard` / `topic_page` / `correlation_csv` / `scan_csv` / `summary_md` / `leaderboard_md` |
| `output_name` | Text | yes | filename |
| `theme_code` | Text | no | if applicable |
| `page_slug` | Text | no | if applicable |
| `generated_at` | DateTime | yes | |
| `status` | Single select | yes | `success` / `failed` / `stale` / `skipped` |
| `trade_date` | Text | no | latest content date |
| `row_count` | Number | no | e.g. correlation CSV rows |
| `file_size_bytes` | Number | no | |
| `url` | URL | no | published URL if any |
| `message` | Long text | no | error or status note |

This table helps answer:

- did a file get generated;
- was it fresh;
- where is it published.

## Optional 7. `cache_manifest`

Purpose:

- track non-Base file assets that remain part of the workflow;
- make file storage observable from Base.

Recommended unique key:

- `run_id + asset_name`

Fields:

| Field | Type | Required | Notes |
|---|---|---:|---|
| `run_id` | Link/Text | yes | |
| `asset_name` | Text | yes | e.g. `sw_daily_full_history.csv` |
| `asset_kind` | Single select | yes | `history_csv` / `parquet` / `artifact_zip` / `release_asset` |
| `storage_backend` | Single select | yes | `github_artifact` / `release_asset` / `repo_file` / `other` |
| `path_or_url` | URL/Text | yes | |
| `row_count` | Number | no | |
| `file_size_bytes` | Number | no | |
| `max_trade_date` | Text | no | |
| `checksum` | Text | no | optional integrity check |

## Optional 8. `industry_daily_agg`

Purpose:

- if you want more history in Base without storing full raw cache;
- one row per `trade_date + industry_code`.

Use only if needed for Base-side charts or retrospective analysis.

Recommended fields:

- `trade_date`
- `industry_code`
- `industry_name`
- `close`
- `pct_change`
- `amount`
- `total_mv_yi`

This is the highest-volume table I would still consider reasonable for Base.

I would not store full per-stock cached series in Base.

## Relationships

Recommended links:

1. `workflow_runs` 1-to-many `industry_scan_daily`
2. `workflow_runs` 1-to-many `theme_correlation_daily`
3. `workflow_runs` 1-to-many `report_publish_daily`
4. `themes_dim` 1-to-many `theme_correlation_daily`

Keep `topic_pages_dim` as a dimension table in v1 without heavy relational modeling.

## Minimal Viable Schema

If we want the smallest useful first release, use only these 4 tables:

1. `workflow_runs`
2. `industry_scan_daily`
3. `theme_correlation_daily`
4. `report_publish_daily`

And keep these outside Base for now:

- `themes_dim` in Python config only
- `topic_pages_dim` in Python config only
- all raw cache files as file artifacts

This is enough to:

- monitor runs;
- inspect latest scan labels;
- inspect latest correlation rankings;
- verify publish completeness.

## Write Strategy From GitHub Actions

Recommended write sequence:

1. create `workflow_runs` row with `status=running`
2. run update pipeline
3. upsert `industry_scan_daily`
4. upsert `theme_correlation_daily`
5. upsert `report_publish_daily`
6. update `workflow_runs` with final status and issue summary

Recommended failure behavior:

- if scan succeeds but publish partially fails, mark run `partial`
- if trade-day guard skips execution, mark run `skipped`
- if Tushare data is stale, mark run `partial` and include issue summary

## Naming Convention

Recommended field naming rule:

- use English snake_case in Base field names;
- keep display labels in Chinese only if the team strongly prefers UI readability.

Reason:

- easier Python mapping;
- easier Actions logs and CLI automation;
- fewer quoting issues.

## First Implementation Recommendation

Recommended first implementation:

1. create `workflow_runs`
2. create `industry_scan_daily`
3. create `theme_correlation_daily`
4. create `report_publish_daily`
5. leave raw cache file storage outside Base

This gives us a stable cloud state layer without overloading Base.

## Open Decisions

These decisions still need alignment before coding:

1. whether `theme_correlation_daily` stores top10 or full ranking;
2. whether `themes_dim` and `topic_pages_dim` live in Base or remain Python config in v1;
3. whether raw cache files are stored as GitHub artifacts, release assets, or repository-managed files;
4. whether `industry_daily_agg` is needed in the first phase.

## Recommended Next Step

After schema confirmation, the next step should be:

1. create the 4-table minimal schema in Feishu Base;
2. add a Python sync layer that writes run status and derived results to Base;
3. keep current CSV/HTML generation unchanged in the first migration phase.

## Buildable V1 Specification

This section turns the design into a buildable first version.

V1 policy:

1. use only simple field types where possible;
2. do not rely on formula or lookup fields in the first build;
3. do not rely on Base-side uniqueness constraints;
4. enforce logical uniqueness in Python sync code.

Recommended Feishu Base field types in V1:

- `Text`
- `Long text`
- `Number`
- `Single select`
- `Checkbox`
- `DateTime`
- `URL`

Do not use these in V1 unless needed later:

- `Formula`
- `Lookup`
- `Link`

Reason:

- simpler table creation;
- easier CLI upsert logic;
- lower migration risk.

## V1 Table Creation Order

Create tables in this order:

1. `workflow_runs`
2. `industry_scan_daily`
3. `theme_correlation_daily`
4. `report_publish_daily`

Optional later:

5. `themes_dim`
6. `topic_pages_dim`

## V1 Enumerations

These single-select values should be created exactly once and reused consistently.

### `workflow_runs.status`

- `running`
- `success`
- `failed`
- `partial`
- `skipped`

### `workflow_runs.trigger_type`

- `schedule`
- `manual`
- `retry`

### `industry_scan_daily.prefilter_label`

Use values from actual scan outputs only. Do not pre-create speculative values.

### `industry_scan_daily.final_label`

Seed with current known values:

- `趋势延续型强势`
- `趋势延续型偏强`
- `接近启动`
- `启动确认`
- `早期启动`
- `观察中`
- `未启动`
- `未纳入主扫描池`
- `数据不足`

### `industry_scan_daily.crowding_label`

Seed with current known values:

- `过热退潮`
- `过热预警`
- `拥挤偏高`
- `拥挤正常`
- `未计算`
- `数据不足`

### `theme_correlation_daily.final_label`

Reuse the same option set as `industry_scan_daily.final_label`.

### `theme_correlation_daily.crowding_label`

Reuse the same option set as `industry_scan_daily.crowding_label`.

### `report_publish_daily.output_type`

- `dashboard`
- `topic_page`
- `correlation_csv`
- `scan_csv`
- `summary_md`
- `leaderboard_md`

### `report_publish_daily.status`

- `success`
- `failed`
- `stale`
- `skipped`

## V1 Table Definitions

### 1. `workflow_runs`

Purpose:

- one row per workflow run;
- highest priority monitoring table.

Recommended row volume:

- about one row per day;
- safe to keep full history in Base.

Fields to create:

| Field name | Feishu type | Required in sync | Example | Notes |
|---|---|---:|---|---|
| `run_id` | Text | yes | `gha_123456789` | logical primary key |
| `workflow_name` | Text | yes | `theme-watch-daily-update` | stable workflow id |
| `trigger_type` | Single select | yes | `schedule` | enum |
| `started_at` | DateTime | yes | `2026-07-08 20:00:03` | local or UTC, but be consistent |
| `finished_at` | DateTime | no | `2026-07-08 20:08:41` | |
| `status` | Single select | yes | `success` | enum |
| `end_date` | Text | yes | `20260708` | requested trade date |
| `is_trade_day` | Checkbox | yes | `true` | |
| `sw_daily_master_max_date` | Text | no | `20260708` | latest raw data date |
| `scan_latest_date` | Text | no | `20260708` | scan date |
| `scan_rows` | Number | no | `88` | |
| `correlation_file_count` | Number | no | `20` | |
| `page_file_count` | Number | no | `19` | official pages only |
| `issues_count` | Number | no | `1` | |
| `issues_summary` | Long text | no | `159998 mapping drift` | concise summary |
| `artifact_url` | URL | no | `https://...` | workflow artifact or release asset |
| `pages_url` | URL | no | `https://...` | publish URL |
| `stdout_excerpt` | Long text | no | `scan_latest_date=...` | optional debug summary |

Recommended indexes in code:

- fetch latest by `started_at`
- fetch by `run_id`
- fetch last successful run by `status=success`

### 2. `industry_scan_daily`

Purpose:

- daily strategy scan result snapshot.

Recommended row volume:

- about `88` rows per run currently;
- very suitable for Base storage.

Logical unique key:

- `snapshot_key = run_id + "::" + industry_code`

Fields to create:

| Field name | Feishu type | Required in sync | Example | Notes |
|---|---|---:|---|---|
| `snapshot_key` | Text | yes | `gha_123::801081.SI` | logical unique key |
| `run_id` | Text | yes | `gha_123` | foreign key by convention |
| `trade_date` | Text | yes | `20260708` | from `latest_date` |
| `industry_code` | Text | yes | `801081.SI` | |
| `industry_name` | Text | yes | `半导体` | |
| `l1_name` | Text | yes | `电子` | |
| `total_mv_yi` | Number | no | `138109.56` | |
| `prefilter_label` | Single select | no | `观察中` | only create actual used values |
| `final_label` | Single select | no | `趋势延续型强势` | |
| `crowding_label` | Single select | no | `过热预警` | |
| `summary_line` | Long text | no | `...` | |
| `leader_top1_name` | Text | no | `中芯国际` | |
| `leader_top1_pct_change` | Number | no | `3.51` | store percent as plain number, not ratio |
| `leader_count` | Number | no | `5` | |
| `leader_active_count` | Number | no | `2` | |
| `absorption_rate` | Number | no | `0.0123` | keep decimal ratio |
| `absorption_rate_rank_pct` | Number | no | `0.98` | keep decimal ratio |
| `absorption_rate_5d_change` | Number | no | `0.0012` | |
| `close_to_ma60_gap` | Number | no | `0.024` | decimal ratio |
| `ma60_slope_20d` | Number | no | `0.031` | decimal ratio |
| `breakout_emerged` | Checkbox | no | `true` | |
| `breakout_confirmed` | Checkbox | no | `false` | |
| `local_activity_ok` | Checkbox | no | `true` | |
| `has_ma250` | Checkbox | no | `true` | |
| `has_amount_ma20` | Checkbox | no | `true` | |
| `has_ret_120d_rank` | Checkbox | no | `true` | |

Fields intentionally excluded from V1:

- all MA raw values
- all leader detail text blobs except `leader_top1_name`
- all boolean internals not needed for dashboards

Those can stay in CSV artifacts first.

### 3. `theme_correlation_daily`

Purpose:

- daily theme correlation ranking snapshot;
- source for homepage mapping drift checks.

Recommended row volume:

- V1 recommended: top `10` rows per theme
- current scale: `20 themes x 10 = 200 rows per run`

Logical unique key:

- `corr_key = run_id + "::" + theme_code + "::" + sw_code`

Fields to create:

| Field name | Feishu type | Required in sync | Example | Notes |
|---|---|---:|---|---|
| `corr_key` | Text | yes | `gha_123::512480.SH::801081.SI` | logical unique key |
| `run_id` | Text | yes | `gha_123` | |
| `trade_date` | Text | yes | `20260708` | run context date |
| `theme_code` | Text | yes | `512480.SH` | |
| `sw_code` | Text | yes | `801081.SI` | |
| `sw_name` | Text | yes | `半导体` | |
| `l1_name` | Text | no | `电子` | |
| `rank_no` | Number | yes | `1` | |
| `corr_daily_ret` | Number | yes | `0.9755` | decimal correlation |
| `common_days` | Number | no | `601` | |
| `final_label` | Single select | no | `趋势延续型强势` | copied from scan |
| `crowding_label` | Single select | no | `过热预警` | copied from scan |
| `total_mv_yi` | Number | no | `138109.56` | copied from scan |
| `leader_top1_name` | Text | no | `中芯国际` | copied from scan |
| `mapped_page_slug` | Text | no | `theme_512480_sw_l2_watch_report.html` | current target page |
| `top_in_page_codes` | Checkbox | no | `true` | useful for drift checks |

Recommended sync policy:

- write top10 per theme in V1;
- if later needed, expand to full ranking without schema change.

### 4. `report_publish_daily`

Purpose:

- track whether expected files were generated and whether they were fresh.

Recommended row volume:

- about `1 dashboard + 19 pages + 20 correlation files + 3 summary files`
- around `43` rows per run if fully tracked

Logical unique key:

- `publish_key = run_id + "::" + output_name`

Fields to create:

| Field name | Feishu type | Required in sync | Example | Notes |
|---|---|---:|---|---|
| `publish_key` | Text | yes | `gha_123::theme_512480_sw_l2_watch_report.html` | logical unique key |
| `run_id` | Text | yes | `gha_123` | |
| `output_type` | Single select | yes | `topic_page` | enum |
| `output_name` | Text | yes | `theme_512480_sw_l2_watch_report.html` | filename |
| `theme_code` | Text | no | `512480.SH` | when applicable |
| `page_slug` | Text | no | `theme_512480_sw_l2_watch_report.html` | when applicable |
| `generated_at` | DateTime | yes | `2026-07-08 20:05:20` | |
| `status` | Single select | yes | `success` | enum |
| `trade_date` | Text | no | `20260708` | latest content date |
| `row_count` | Number | no | `124` | for correlation CSV |
| `file_size_bytes` | Number | no | `130775` | |
| `url` | URL | no | `https://...` | publish URL if available |
| `message` | Long text | no | `stale leftover page` | status note |

## Minimal Build Checklist

If we are building the first Base manually, create only these fields first:

### `workflow_runs`

- `run_id`
- `workflow_name`
- `trigger_type`
- `started_at`
- `finished_at`
- `status`
- `end_date`
- `is_trade_day`
- `sw_daily_master_max_date`
- `scan_latest_date`
- `scan_rows`
- `issues_count`
- `issues_summary`

### `industry_scan_daily`

- `snapshot_key`
- `run_id`
- `trade_date`
- `industry_code`
- `industry_name`
- `l1_name`
- `final_label`
- `crowding_label`
- `summary_line`
- `leader_top1_name`
- `leader_top1_pct_change`
- `absorption_rate_rank_pct`

### `theme_correlation_daily`

- `corr_key`
- `run_id`
- `trade_date`
- `theme_code`
- `sw_code`
- `sw_name`
- `rank_no`
- `corr_daily_ret`
- `common_days`
- `final_label`
- `crowding_label`
- `mapped_page_slug`
- `top_in_page_codes`

### `report_publish_daily`

- `publish_key`
- `run_id`
- `output_type`
- `output_name`
- `generated_at`
- `status`
- `trade_date`
- `row_count`
- `file_size_bytes`
- `message`

## V1 Data Mapping Rules

These rules should be followed consistently in sync code.

1. Percent-like market move fields such as `leader_top1_pct_change` should be stored as plain percent numbers like `3.51`, not `0.0351`.
2. Ratio-like analytical fields such as `corr_daily_ret`, `absorption_rate`, `absorption_rate_rank_pct`, `close_to_ma60_gap` should be stored as decimal values like `0.9755` or `0.0241`.
3. Trade dates should stay as text `YYYYMMDD` in V1 to avoid timezone and date-only parsing issues.
4. Timestamps such as `started_at`, `finished_at`, `generated_at` should use one timezone consistently. Recommended: Asia/Shanghai local time strings.
5. Missing booleans should be omitted or left blank rather than coerced to `false`.

## V1 Decisions Recommended Now

To keep momentum, I recommend these default choices:

1. `theme_correlation_daily` stores top10, not full ranking.
2. `themes_dim` and `topic_pages_dim` stay in Python config in V1.
3. Raw cache files stay outside Base.
4. `industry_daily_agg` is deferred.

## Next Step After This Spec

Once this spec is accepted, the next concrete step should be one of:

1. create the 4 MVP tables manually in Feishu Base using this field list;
2. scaffold a Python sync module that writes to these 4 tables;
3. optionally create `themes_dim` and `topic_pages_dim` later for stronger Base-side governance.

---
sop:
  id: "etf_constituent_watch"
  version: "1.2.0"
  canonical_path: "industry_insight_sandbox/ETF_CONSTITUENT_WATCH_MACHINE_SOP.md"
  document_kind: "machine_execution_contract"
  audience:
    - "automation"
    - "ai_agent"
    - "code_generator"
    - "workflow_runner"
  language: "zh-CN"
  parse_contract:
    container: "yaml_frontmatter"
    body_required: false
    unknown_key_policy: "ignore"
    missing_required_key_policy: "halt"
  required_top_level_keys:
    - "sop"
    - "authority"
    - "invariants"
    - "strategy"
    - "label_state_machine"
    - "execution"
    - "validation"
    - "publication"
    - "secrets"
    - "failure_contract"
  last_verified:
    date: "2026-07-24"
    implementation_baseline_ref: "same_git_commit_as_this_file"

authority:
  on_conflict: "halt_with_SOP_DRIFT_DETECTED"
  strategy_engine: "industry_insight_sandbox/generate_dashboard_data.py"
  target_universe: "industry_insight_sandbox/targets.json"
  local_orchestrator: "run_etf_constituent_workflow.py"
  ci_orchestrator: ".github/workflows/etf-constituent-daily.yml"
  scheduled_readiness_checker: "industry_insight_sandbox/check_tushare_readiness.py"
  rendered_page_tests: "industry_insight_sandbox/tests/rendered-html.test.mjs"
  overview_sorting: "industry_insight_sandbox/app/page.tsx"
  webhook_sender: "etf_constituent_feishu_webhook.py"
  dependency_files:
    python: "requirements-etf-constituent.txt"
    node: "industry_insight_sandbox/package-lock.json"

invariants:
  strategy_relation:
    etf: "ETF -> 真实跟踪指数 -> 指数权重核心成分股"
    direct_index: "主题指数 -> 自身指数行情 -> 指数权重核心成分股"
  sw_l2_role: "display_only"
  sw_l2_must_not_affect_label: true
  isolated_from_workflows:
    - "run_theme_watch_workflow.py"
    - "run_sw_l2_strategy_scan.py"
  forbidden_data_paths:
    - ".cache_scan_v2"
    - "reports/theme_watch"
  target_count: 20
  target_kind_counts:
    etf: 19
    index: 1
  stage_count: 3
  stage_ids_in_order:
    - "structure"
    - "breakout"
    - "leader"
  benchmark_code: "000300.SH"
  history_start: "20240101"
  production_url: "https://etf-core-constituent-watch.vercel.app"

target_universe:
  source_file: "industry_insight_sandbox/targets.json"
  source_is_authoritative: true
  duplicate_target_definitions_in_this_sop: false
  required_fields:
    - "bucket"
    - "code"
    - "name"
    - "kind"
    - "order"
  allowed_kind:
    - "etf"
    - "index"
  slug_formula: "lower(code).replace('.', '-')"

data:
  provider: "Tushare Pro"
  token_source: "TUSHARE_TOKEN"
  timezone: "Asia/Shanghai"
  history:
    start_date: "20240101"
    end_date: "${end_date:YYYYMMDD}"
  weight_query:
    start_date_formula: "first_day(end_date - 210 calendar days)"
    end_date_formula: "${end_date}"
    selected_snapshot: "max(trade_date)"
    lookahead_allowed: false
  endpoints:
    etf_metadata:
      api: "etf_basic"
      refresh_each_run: true
      required_fields:
        - "ts_code"
        - "extname"
        - "cname"
        - "index_code"
        - "index_name"
        - "exchange"
        - "mgr_name"
    stock_metadata:
      api: "stock_basic"
      refresh_each_run: true
      required_fields:
        - "ts_code"
        - "name"
        - "industry"
        - "market"
    etf_daily:
      api: "fund_daily"
    index_daily:
      api: "index_daily"
    index_weights:
      api: "index_weight"
    component_daily:
      api: "daily"
    full_market_daily_amount:
      api: "daily"
      query_mode: "one trade_date per request"
      aggregation: "sum(amount)"
    trade_calendar:
      api: "trade_cal"
      exchange: "SSE"
  fetch_retry:
    attempts: 3
    backoff_seconds_by_retry:
      - 2
      - 4
  cache:
    directory: "industry_insight_sandbox/data/cache"
    restored_by_github_actions: true
    saved_by_github_actions: true

component_selection:
  weight_sort: "descending"
  core_weight_coverage_percent: 60.0
  minimum_core_count: 3
  maximum_core_count: 20
  count_formula: "min(max(3, first_rank_where_cumulative_weight_reaches_60_percent), 20, available_weight_rows)"
  leader_watch_count: 10
  strict_leader_count: 3
  history_fetch_count_formula: "max(core_count, 10)"
  missing_component_history_policy: "skip_component"
  no_usable_component_policy: "fail_target"
  freshness:
    cutoff_formula: "component.trade_date <= target.latestDate"
    fresh_formula: "component.latest_trade_date == target.latestDate"
    future_rows_allowed_in_decision: false
    stale_component_can_pass_above_ma: false
    stale_component_can_count_as_active: false
    stale_component_can_confirm_leader: false

strategy:
  numeric_comparison:
    equality_counts_as_above_ma: true
    null_indicator_policy: "condition_false"

  indicators:
    ma60:
      input: "tracking_index.close"
      window_trade_days: 60
      function: "simple_moving_average"
    ma250:
      input: "tracking_index.close"
      window_trade_days: 250
      function: "simple_moving_average"
    low_window:
      window_trade_days: 120
      completeness_required: true
      complete_condition: "count(rows_with_non_null_ma250) == 120"
    amount_ratio20:
      input: "sum(core_component.amount)"
      formula: "current_core_amount / rolling_mean(core_amount, 20)"
      role: "diagnostic_only"
    absorption_rate:
      formula: "tracking_index.amount / full_A_share_market.amount"
    absorption_rank_pct:
      formula: "rolling_rank_pct(absorption_rate)"
      rolling_window_trade_days: 252
      minimum_observations: 120
    relative_excess_120:
      aligned_rows: 121
      formula: "(tracking_index_close_last / tracking_index_close_first - 1) - (benchmark_close_last / benchmark_close_first - 1)"
      benchmark: "000300.SH"
    core_component_active:
      formula: "pct_change_1d >= 5.0 OR return_5d >= 5.0"
    close_to_high_120:
      formula: "latest_tracking_index_close / max(tracking_index_close_last_120)"

  stage_structure:
    id: "structure"
    title: "低位收敛"
    prerequisites:
      - "low_window.complete_condition"
    pass_formula: "path_a.pass OR path_b.pass"
    warning_formula: "NOT pass AND (path_a.warning OR path_b.warning)"
    path_a:
      metric: "count(close < ma250 in last 120 trade days)"
      warning_threshold_days: 40
      pass_threshold_days: 60
    path_b:
      metric: "count(close <= ma250 * 0.90 in last 120 trade days)"
      warning_threshold_days: 12
      pass_threshold_days: 24
    diagnostic_only:
      metric: "count(close <= ma250 * 0.85 in last 120 trade days)"
      affects_pass: false
      affects_warning: false

  stage_breakout:
    id: "breakout"
    title: "带量突破年线"
    ma60_early_warning:
      formula: "latest_close >= latest_ma60"
      pass_replacement_allowed: false
      breakout_today_formula: "previous_close < previous_ma60 AND latest_close >= latest_ma60"
      streak_formula: "count_consecutive_latest_days(close >= ma60)"
    price_confirmation:
      formula: "last_2_trade_days_all(close >= ma250)"
      minimum_gap_percent: 0.0
    funding_confirmation:
      formula: "last_3_trade_days_all(absorption_rank_pct >= 0.80)"
      percentile_threshold: 0.80
      consecutive_trade_days: 3
    pass_formula: "price_confirmation AND funding_confirmation"
    emerged_formula: "price_confirmation OR funding_confirmation"
    warning_formula: "ma60_early_warning AND NOT pass"
    crowding_risk:
      current_hot_formula: "latest_absorption_rank_pct >= 0.95"
      overheated_formula: "last_3_trade_days_all(absorption_rank_pct >= 0.95)"
      affects_pass: false

  stage_leader:
    id: "leader"
    title: "权重龙头确认"
    watched_ranks:
      strict:
        from: 1
        to: 3
        event_window_trade_days: 5
      secondary:
        from: 4
        to: 10
        event_window_trade_days: 3
    window_calendar:
      source: "tracking_index.trade_date"
      slicing_order: "slice_last_N_market_trade_dates_before_aligning_component_rows"
      alignment: "left_align_component_daily_to_market_trade_dates"
      component_own_tail_allowed: false
      rows_after_target_date_allowed: false
    limit_up_threshold_pct:
      star_market_or_chinext:
        code_prefixes:
          - "688"
          - "300"
        threshold: 19.5
      beijing_stock_exchange:
        code_prefixes:
          - "8"
          - "4"
        threshold: 29.5
      default:
        threshold: 9.5
    event_selection: "latest_limit_event_in_window"
    continuation:
      known_formula: "component_has_record_on_immediate_next_market_trade_date"
      positive_next_day_formula: "immediate_next_market_trade_date.pct_chg > 0"
      strict_latest_retained_formula: "data_fresh AND latest_close >= limit_event_close"
      strict_qualified_formula: "data_fresh AND positive_next_day AND strict_latest_retained"
      secondary_qualified_formula: "data_fresh AND positive_next_day"
      missing_next_market_trade_day_record: "unqualified"
    strict_limit_seen_formula: "exists(limit_event where weight_rank <= 3 AND data_fresh)"
    secondary_alert_formula: "exists(qualified_limit_event where 4 <= weight_rank <= 10)"
    group_monitor:
      formula: "active_core_count >= 1 AND above_ma60_core_count / usable_core_count >= 0.50"
      affects_strict_pass: false
    pass_formula: "exists(strict_qualified_limit_event)"
    warning_formula: "(strict_limit_seen OR secondary_alert OR group_monitor) AND NOT pass"

  trend_extension:
    formula: "condition_a OR condition_b OR condition_c"
    condition_a: "latest_close > latest_ma250 * 1.15"
    condition_b: "relative_excess_120 >= 0.15"
    condition_c: "close_to_high_120 >= 0.95 AND above_ma60_core_ratio >= 0.67 AND above_ma250_core_ratio >= 0.67"
    evaluation_priority: 1

label_state_machine:
  evaluation_mode: "first_match_wins"
  states_in_priority_order:
    - label: "趋势延续"
      condition: "trend_extension"
    - label: "启动确认"
      condition: "structure.pass AND breakout.pass AND leader.pass"
    - label: "接近启动"
      condition: "structure.pass AND breakout.emerged AND leader.group_monitor"
    - label: "观察中"
      condition: "structure.pass OR structure.warning OR breakout.ma60_early_warning OR breakout.emerged OR leader.strict_limit_seen OR leader.secondary_alert OR leader.group_monitor"
    - label: "未启动"
      condition: "otherwise"
  stage_pass_count_formula: "sum(structure.pass, breakout.pass, leader.pass)"
  overview_sort:
    label_order:
      - "趋势延续"
      - "启动确认"
      - "接近启动"
      - "观察中"
      - "未启动"
    tie_breakers_in_order:
      - "stage_pass_count descending"
      - "absorption_rank_pct descending; null treated as 0"
      - "target.order ascending"

execution:
  local:
    working_directory: "repository_root"
    install_command: "python -m pip install -r requirements-etf-constituent.txt"
    run_command: "py -B ./run_etf_constituent_workflow.py --end-date ${end_date:YYYYMMDD} --trigger-type manual"
    validate_only_command: "py -B ./run_etf_constituent_workflow.py --end-date ${end_date:YYYYMMDD} --validate-only"
    allow_non_trade_day_flag: "--allow-non-trade-day"
    default_end_date:
      before_local_hour_16: "previous_calendar_day"
      at_or_after_local_hour_16: "current_calendar_day"
    trade_day_policy:
      calendar: "SSE"
      non_trade_day_without_override: "status_skipped_exit_0"
      validate_only_checks_trade_day: false

  github_actions:
    workflow_file: ".github/workflows/etf-constituent-daily.yml"
    permissions:
      contents: "write"
    triggers:
      schedule:
        cron: "5 21 * * 1-5"
        timezone: "Asia/Shanghai"
      workflow_dispatch:
        inputs:
          end_date:
            format: "YYYYMMDD"
            required: false
          allow_non_trade_day:
            type: "boolean"
            default: false
      push:
        branches:
          - "main"
        path_filters:
          - ".github/workflows/etf-constituent-daily.yml"
          - "etf_constituent_feishu_webhook.py"
          - "run_etf_constituent_workflow.py"
          - "requirements-etf-constituent.txt"
          - "industry_insight_sandbox/**"
    scheduled_data_readiness:
      applies_to_event: "schedule"
      target_date_formula: "current_date_in_Asia/Shanghai"
      non_trading_day_result: "data_ready_false"
      target_source: "industry_insight_sandbox/targets.json"
      target_source_checkout_required: true
      etf_tracking_index_resolution:
        metadata_api: "etf_basic"
        metadata_fields:
          - "ts_code"
          - "index_code"
          - "index_name"
        etf_target_formula: "all targets where kind == etf"
        direct_index_formula: "all targets where kind == index"
        tracking_index_formula: "unique(etf_basic.index_code for every ETF target) UNION direct index target codes"
        unresolved_etf_mapping_result: "data_ready_false"
      probes:
        stock_daily:
          api: "daily"
          minimum_rows: 1000
          required_trade_date: "${target_date}"
        all_etf_targets:
          api: "fund_daily"
          codes: "every ETF code from target_source"
          minimum_rows: 1
          required_trade_date: "${target_date}"
          missing_any_code_result: "data_ready_false"
        all_tracking_indexes:
          api: "index_daily"
          codes: "every resolved tracking index plus every direct index target"
          minimum_rows: 1
          required_trade_date: "${target_date}"
          missing_any_code_result: "data_ready_false"
      query_control:
        retry_attempts: 3
        retry_backoff_seconds:
          - 2
          - 4
        throttle_seconds_between_symbol_queries: 0.35
      calculate_job_condition: "all_probes_ready"
    calculate_and_publish_steps_in_order:
      - "checkout"
      - "setup_python_3_11"
      - "setup_node_22"
      - "restore_market_data_cache"
      - "install_python_dependencies"
      - "npm_ci"
      - "run_etf_constituent_workflow"
      - "npm_test_if_calculation_success"
      - "vercel_pull_production_if_calculation_success"
      - "vercel_build_production_if_calculation_success"
      - "vercel_deploy_production_if_calculation_success"
      - "force_publish_json_to_etf-watch-data_if_calculation_success"
      - "upload_logs_always"
      - "upload_observation_snapshot_if_calculation_success"
      - "send_feishu_webhook_always"
      - "save_market_data_cache_always"

validation:
  local_orchestrator_output_contract:
    stdout_keys:
      - "run_id"
      - "status"
      - "issues_count"
      - "target_count"
      - "latest_date"
      - "labels"
      - "summary_json"
      - "stdout_log"
    status_enum:
      - "success"
      - "failed"
      - "skipped"
    failed_status_exit_code: 1
    skipped_status_exit_code: 0
  generated_data_checks:
    target_count: 20
    etf_count: 19
    index_count: 1
    overview_codes_equal_target_codes: true
    topic_codes_equal_target_codes: true
    topic_file_slugs_equal_target_slugs: true
    overview_sandbox_flag: true
    every_latest_date_equals_end_date: true
    every_topic_sandbox_flag: true
    every_topic_has_tracking_index_metadata: true
    minimum_chart_rows_per_topic: 250
    minimum_core_components_per_topic: 3
    core_count_equals_component_rows: true
    required_stage_titles_in_order:
      - "低位收敛"
      - "带量突破年线"
      - "权重龙头确认"
  site_test:
    command: "cd industry_insight_sandbox && npm test"
    expected_python_behavior_test_count: 19
    expected_node_render_test_count: 8
    behavior_test_files:
      - "industry_insight_sandbox/tests/test_strategy_behavior.py"
      - "industry_insight_sandbox/tests/test_readiness_behavior.py"
    required_behavior_cases:
      - "stale_component_own_tail_event_excluded"
      - "stale_latest_component_unqualified"
      - "missing_immediate_next_market_trade_day_unqualified"
      - "exact_limit_threshold_boundary"
      - "future_rows_excluded"
      - "secondary_rank_uses_three_market_trade_days"
      - "board_specific_limit_thresholds"
      - "structure_path_a_warning_and_pass_boundaries"
      - "structure_path_b_warning_and_pass_boundaries"
      - "incomplete_structure_window_cannot_warn_or_pass"
      - "ma_equality_and_funding_threshold_boundaries"
      - "funding_below_threshold_blocks_confirmation"
      - "missing_breakout_market_days_cannot_confirm"
      - "ma60_equality_counts_as_breakout"
      - "readiness_resolves_every_etf_and_direct_index"
      - "readiness_deduplicates_shared_tracking_indexes"
      - "readiness_reports_missing_tracking_metadata"
      - "readiness_rejects_unsupported_target_kind"
      - "readiness_requires_target_date_and_minimum_rows"
  vercel_build_test:
    command: "cd industry_insight_sandbox && npm run build:vercel"
  required_outputs:
    - "industry_insight_sandbox/data/overview.json"
    - "industry_insight_sandbox/data/all_topics.json"
    - "industry_insight_sandbox/data/topics/<slug>.json"
    - "logs/etf_constituent_workflow/<run_id>.json"
    - "logs/etf_constituent_workflow/<run_id>.log"

output_schema:
  overview:
    path: "industry_insight_sandbox/data/overview.json"
    required_meta_fields:
      - "generatedAt"
      - "targetCount"
      - "etfCount"
      - "indexCount"
      - "source"
      - "sandbox"
    required_target_fields:
      - "slug"
      - "code"
      - "name"
      - "kind"
      - "indexCode"
      - "indexName"
      - "label"
      - "latestDate"
      - "weightDate"
      - "ma250Gap"
      - "absorptionRankPct"
      - "fundingConfirmed"
      - "crowdingHot"
      - "belowMa250Days"
      - "belowMa250TenDays"
      - "stagePassCount"
      - "stageStates"
    required_component_freshness_fields:
      - "latestDate"
      - "dataFresh"
  topic:
    aggregate_path: "industry_insight_sandbox/data/all_topics.json"
    individual_path_template: "industry_insight_sandbox/data/topics/<slug>.json"
    required_sections:
      - "meta"
      - "target"
      - "summary"
      - "stages"
      - "chart"
      - "weights"
      - "components"
      - "limitEvents"
      - "notes"

publication:
  live_data:
    repository: "keycool/theme_watch"
    branch: "etf-watch-data"
    update_mode: "force_push_generated_json_only"
    files:
      - "overview.json"
      - "all_topics.json"
      - "topics/**"
  web_application:
    provider: "Vercel"
    project_name: "etf-core-constituent-watch"
    root_directory: "industry_insight_sandbox"
    production_url: "https://etf-core-constituent-watch.vercel.app"
    framework: "Next.js"
    build_command: "npm run build:vercel"
    client_data_source: "https://raw.githubusercontent.com/keycool/theme_watch/etf-watch-data/overview.json"
    live_fetch_cache: "no-store"
    live_data_accept_condition: "meta.targetCount == 20"
    live_fetch_failure_fallback: "bundled_build_snapshot"
  artifacts:
    logs_name: "etf-constituent-workflow-logs"
    snapshot_name_template: "etf-constituent-observation-${github.run_id}"
  feishu:
    send_condition: "always"
    site_url: "https://etf-core-constituent-watch.vercel.app"
    keyword: "theme_watch"

secrets:
  required:
    - name: "TUSHARE_TOKEN"
      consumer:
        - "scheduled_data_readiness"
        - "strategy_generator"
    - name: "VERCEL_TOKEN"
      consumer:
        - "vercel_cli"
    - name: "VERCEL_ORG_ID"
      consumer:
        - "vercel_cli"
    - name: "VERCEL_PROJECT_ID"
      consumer:
        - "vercel_cli"
    - name: "Theme_Watch_FEISHU_WEBHOOK_URL"
      consumer:
        - "feishu_webhook"
    - name: "Theme_Watch_FEISHU_WEBHOOK_SECRET"
      consumer:
        - "feishu_webhook"
  secret_values_must_not_appear_in:
    - "this_sop"
    - "git"
    - "stdout"
    - "artifacts"

failure_contract:
  stop_publication_when:
    - "generator_exit_code_nonzero"
    - "generated_data_validation_failed"
    - "npm_test_failed"
    - "vercel_pull_failed"
    - "vercel_build_failed"
    - "vercel_deploy_failed"
  publication_order_invariant: "vercel_pull_and_build_and_deploy_success_before_etf_watch_data_force_push"
  preserve_and_upload_logs_on_failure: true
  send_feishu_on_failure: true
  save_cache_on_failure: true
  error_codes:
    missing_tushare_token: "TUSHARE_TOKEN_MISSING"
    non_trade_day: "SKIPPED_NON_TRADE_DAY"
    scheduled_data_incomplete: "TUSHARE_DAILY_DATA_NOT_READY"
    target_count_mismatch: "TARGET_UNIVERSE_MISMATCH"
    missing_target_data: "TARGET_DATA_INCOMPLETE"
    missing_component_data: "NO_USABLE_CORE_COMPONENTS"
    generated_output_invalid: "GENERATED_OUTPUT_VALIDATION_FAILED"
    site_test_failed: "SITE_RENDER_VALIDATION_FAILED"
    vercel_binding_failed: "VERCEL_PROJECT_BINDING_FAILED"
    vercel_build_failed: "VERCEL_BUILD_FAILED"
    vercel_deploy_failed: "VERCEL_DEPLOY_FAILED"
    sop_drift: "SOP_DRIFT_DETECTED"

change_control:
  strategy_threshold_change_requires:
    - "update industry_insight_sandbox/generate_dashboard_data.py"
    - "update industry_insight_sandbox/tests/rendered-html.test.mjs"
    - "update this SOP"
    - "run npm test"
    - "run npm run build:vercel"
  workflow_change_requires:
    - "update .github/workflows/etf-constituent-daily.yml"
    - "update this SOP when execution order, trigger, secret, output, or publication behavior changes"
    - "parse workflow YAML"
  target_universe_change_requires:
    - "update industry_insight_sandbox/targets.json"
    - "update expected target counts in run_etf_constituent_workflow.py and tests"
    - "update this SOP invariants"
  prohibited_behavior:
    - "silently infer a replacement threshold"
    - "silently use SW L2 to determine labels"
    - "publish when validation status is failed"
    - "log secret values"
---

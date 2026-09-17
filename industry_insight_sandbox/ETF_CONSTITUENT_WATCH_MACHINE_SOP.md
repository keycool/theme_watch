---
sop:
  id: "etf_constituent_watch"
  version: "2.1.12"
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
    date: "2026-08-14"
    implementation_baseline_ref: "same_git_commit_as_this_file"

authority:
  on_conflict: "halt_with_SOP_DRIFT_DETECTED"
  strategy_engine: "industry_insight_sandbox/generate_dashboard_data.py"
  moving_average_lifecycle_engine: "industry_insight_sandbox/moving_average_lifecycle.py"
  target_universe: "industry_insight_sandbox/targets.json"
  hk_qdii_target_universe: "industry_insight_sandbox/hk_qdii_targets.json"
  hk_qdii_strategy_engines:
    - "industry_insight_sandbox/generate_hk_qdii_dashboard_data.py"
    - "industry_insight_sandbox/generate_hk_connect_consumer_dashboard_data.py"
  unified_overview_merger: "industry_insight_sandbox/merge_hk_qdii_overview.py"
  allocation_handoff_builder: "industry_insight_sandbox/build_allocation_handoff.py"
  signal_followup_builder: "industry_insight_sandbox/update_signal_followup.py"
  offline_backtest_runner: "industry_insight_sandbox/backtest_etf_watch.py"
  expanded_universe_research_runner: "industry_insight_sandbox/expanded_universe_research.py"
  offline_backtest_review: "industry_insight_sandbox/ETF_CONSTITUENT_WATCH_BACKTEST_REVIEW_2026-08-13.md"
  offline_execution_simulator: "industry_insight_sandbox/backtest_execution_discipline.py"
  offline_execution_review: "industry_insight_sandbox/ETF_WATCH_EXECUTION_DISCIPLINE_REVIEW_2026-08-14.md"
  review_record: "industry_insight_sandbox/ETF_CONSTITUENT_WATCH_REVIEW_2026-08-13.md"
  parameter_ledger: "industry_insight_sandbox/ETF_CONSTITUENT_WATCH_PARAMETER_LEDGER.md"
  local_orchestrator: "run_etf_constituent_workflow.py"
  ci_orchestrator: ".github/workflows/etf-constituent-daily.yml"
  scheduled_readiness_checker: "industry_insight_sandbox/check_tushare_readiness.py"
  trade_date_selector: "industry_insight_sandbox/trading_calendar.py"
  production_date_guard: "industry_insight_sandbox/guard_production_date.py"
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
  target_count: 25
  core_target_count: 23
  hk_qdii_target_count: 2
  target_kind_counts:
    etf_total: 24
    index: 1
    hk_qdii_etf: 2
  stage_count: 3
  stage_ids_in_order:
    - "structure"
    - "breakout"
    - "leader"
  moving_average_lifecycle_is_independent_from_primary_label: true
  benchmark_code: "000300.SH"
  history_start: "20190101"
  production_url: "https://etf-core-constituent-watch.vercel.app"

target_universe:
  source_file: "industry_insight_sandbox/targets.json"
  source_is_authoritative_for_core_targets: true
  hk_qdii_source_file: "industry_insight_sandbox/hk_qdii_targets.json"
  hk_qdii_source_is_authoritative: true
  unified_formula: "targets.json UNION hk_qdii_targets.json"
  duplicate_target_definitions_in_this_sop: false
  required_fields:
    - "bucket"
    - "code"
    - "name"
    - "kind"
    - "order"
  allowed_core_kind:
    - "etf"
    - "index"
  allowed_hk_qdii_kind:
    - "hk_qdii"
  slug_formula: "lower(code).replace('.', '-')"

data:
  provider: "Tushare Pro"
  token_source: "TUSHARE_TOKEN"
  timezone: "Asia/Shanghai"
  history:
    start_date: "20190101"
    end_date: "${end_date:YYYYMMDD}"
    long_cycle_min_trade_days: 750
    long_cycle_definition: "MA250 warm-up plus 500 additional trade-day observations"
    primary_label_formula_changes_when_insufficient: false
    allocation_entry_allowed_when_insufficient: false
  weight_query:
    start_date_formula: "first_day(end_date - 210 calendar days)"
    end_date_formula: "${end_date}"
    selected_snapshot: "max(trade_date)"
    lookahead_allowed: false
    actual_age_output_required: true
    allocation_freshness_max_calendar_days: 60
    stale_weight_changes_primary_label: false
    stale_weight_blocks_new_entry_or_scaling: true
    future_weight_snapshot_allowed: false
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
  usage_contract:
    role: "observation_only_auxiliary_information"
    conclusion: "expanded_sample_does_not_support_using_this_strategy_as_an_independent_capital_allocation_strategy"
    effective_consumer_mode: "observe_only"
    capital_allocation_authority: "none"
    order_authority: "none"
    external_monitor_role: "read_signals_as_context_for_a_separate_monitoring_model; do_not_convert_them_to_orders_or_position_sizes"
    allowed_uses:
      - "display_primary_label_and_three_stage_evidence"
      - "display_moving_average_lifecycle_as_an_observation_signal"
      - "display_data_freshness_weight_age_and_etf_liquidity_guards"
      - "queue_for_human_review_or_cross_system_comparison"
      - "record_signal_followup_as_post_event_research_only"
    prohibited_uses:
      - "open_position"
      - "add_position"
      - "reduce_position"
      - "close_position"
      - "calculate_cny_amount_or_account_weight"
      - "rank_targets_as_expected_return_or_priority_to_trade"
    legacy_wire_fields:
      meaning: "allocation_handoff.json remains available for schema compatibility"
      consumer_rule: "action, targetAllocationUnits, allocationInstruction and positionSignal are non-operative metadata; treat every record as observe_only"
      do_not_infer: "starter, confirmed, risk_protection, exit or extended must not be interpreted as an executable capital instruction"
  numeric_comparison:
    equality_counts_as_above_ma: true
    null_indicator_policy: "condition_false"

  indicators:
    ma20:
      input: "tracking_index.close"
      window_trade_days: 20
      function: "simple_moving_average"
      role: "diagnostic_and_auxiliary_label"
      affects_stage_or_primary_label: false
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

  short_term_rhythm:
    output_field: "rhythmLabel"
    role: "auxiliary_label_only"
    affects_stage_or_primary_label: false
    ma20_rising_formula: "latest_ma20 > ma20_5_trade_days_ago"
    evaluation_mode: "first_match_wins"
    states_in_priority_order:
      - label: "短期转强"
        condition: "latest_close >= latest_ma20 AND latest_ma20 >= latest_ma60 AND ma20_rising"
      - label: "低位反弹"
        condition: "latest_close >= latest_ma20 AND latest_ma20 < latest_ma60"
      - label: "上升回踩"
        condition: "latest_close < latest_ma20 AND latest_ma20 >= latest_ma60 AND ma20_rising"
      - label: "短期转弱"
        condition: "latest_close < latest_ma20 AND NOT ma20_rising"
      - label: "震荡整理"
        condition: "otherwise_or_missing_indicator"

  moving_average_lifecycle:
    output_field: "maLifecycle"
    role: "independent_startup_timing_signal"
    affects_stage_or_primary_label: false
    lookahead_allowed: false
    calculation_object: "same_price_series_used_for_ma20_ma60_ma250"
    safety_margin:
      formula: "(ma250 - ma60) / ma250"
      eligible_regime: "ma60 < ma250"
      historical_window_trade_days: 500
      historical_rows: "strictly_before_signal_date"
      minimum_eligible_observations: 120
      dynamic_percentile_threshold: 0.70
      absolute_minimum_separation: 0.05
      pass_formula: "separation >= 0.05 AND prior_history_percentile_rank >= 0.70"
    predecessor_path:
      death_cross_required: true
      death_cross_formula: "previous_ma60 >= previous_ma250 AND current_ma60 < current_ma250"
      death_cross_lookback_trade_days: 500
      convergence_window_trade_days: 30
      convergence_required_days: 20
      convergence_day_formula: "close < ma20 AND ma20 < ma60"
      warm_up_cross_formula: "previous_close < previous_ma20 AND current_close >= current_ma20"
      warm_up_must_precede_initial_start: true
      warm_up_lookback_trade_days: 20
    events:
      warm_up:
        label: "短线转暖"
        role: "observation_only"
      initial_start:
        label: "初始启动"
        formula: "predecessor_path_passed AND safety_margin_passed AND previous_close < previous_ma60 AND current_close >= current_ma60"
        capital_interface: "legacy_observation_field_only"
      trend_confirmation:
        label: "年线趋势确认"
        formula: "after_initial_start AND previous_close < previous_ma250 AND current_close >= current_ma250"
        confirmation_timing: "same_trade_day_as_ma250_upward_cross"
        capital_interface: "legacy_observation_field_only"
    state_activity:
      initial_start_active: "valid_initial_start_exists AND latest_close >= latest_ma60 AND NOT trend_confirmed_active"
      trend_confirmed_active: "valid_trend_confirmation_exists AND latest_close >= latest_ma250"
      invalidated_initial_start: "valid_initial_start_exists AND latest_close < latest_ma60 AND NOT trend_confirmed_active"
    capital_execution:
      allocation_mode: "observation_only"
      strategy_role: "auxiliary_observation_only; not a funded core or satellite strategy"
      owner: "external_monitor_reads_context_only"
      strategy_executes_orders: false
      fixed_cny_amount_provided: false
      allocation_unit_owner: "none_for_this_strategy"
      allocation_unit_definition: "no allocation unit is defined; any external budget model belongs to a separate monitor"
      observe_only_interface: "observe_only"

  allocation_handoff:
    output_path: "industry_insight_sandbox/data/allocation_handoff.json"
    schema_version: "1.3"
    allocation_mode: "event_driven_satellite"
    effective_consumer_mode: "observation_only"
    compatibility_only: true
    owner: "external_monitor"
    strategy_executes_orders: false
    position_sizing_provided: false
    fixed_cny_amount_provided: false
    allocation_unit_owner: "external_monitor"
    leader_confirmation_role: "industry_state_confirmation_only"
    leader_stock_chase_allowed: false
    leader_confirmation_availability: "after_immediate_next_market_trade_day_close"
    etf_liquidity_role: "execution_metadata_only; it does not replace tracking-index absorption confirmation"
    premium_discount_check_owner: "external_monitor"
    allocation_unit_model:
      purpose: "compatibility metadata only; no relative capacity or position size is defined"
      all_values: "ignore_for_capital_decisions"
      observe_only: "effective meaning for every record"
      candidate_entry: "legacy label only; observe_only"
      starter_eligible: "legacy label only; observe_only"
      scale_in_eligible: "legacy label only; observe_only"
      reduce_to_one_unit: "legacy label only; observe_only"
      hold_and_monitor: "legacy label only; observe_only"
      de_risk: "legacy label only; observe_only"
    output_fields:
      allocationMode: "event_driven_satellite"
      allocationUnitOwner: "external_monitor"
      targetAllocationUnits: "wire compatibility field; ignore regardless of value"
      allocationInstruction: "wire compatibility field; never an instruction to act"
      positionSignal: "observation metadata only; never a position or risk action"
    position_signal_state_machine:
      independent_from_primary_label: true
      primary_label_role: "input only; it must not be changed by this state machine"
      states:
        watch: "observe_only"
        candidate: "observe_only; legacy stage label"
        starter: "observe_only; legacy stage label"
        confirmed: "observe_only; legacy stage label"
        extended: "observe_only; legacy stage label"
        risk_protection: "observe_only; legacy risk context"
        exit: "observe_only; legacy risk context"
        data_guard: "observe_only; data-quality warning"
      entry_guards:
        - "all component freshness fields are complete and current"
        - "longCycleHistoryReady == true"
        - "weightFresh == true"
      execution_metadata:
        weight_age: "weightDate to topic asOf in calendar days"
        etf_amount_rank_pct: "ETF own amount rolling 252-day percentile with min 120 observations"
        premium_discount: "not provided by this strategy; external monitor must check before execution"
      risk_rules:
        ma20_profit_protection: "last_2_trade_days_all(close < ma20) AND latest_ma20 < ma20_5_trade_days_ago; advisory only and requires external position state"
        ma60_structure_exit: "(initial_start_active OR trend_confirmed_active) AND latest_close < latest_ma60; advisory only and requires external position state"
        funding_or_leader_risk: "not an automatic exit rule; funding remains a confirmed-stage quality gate and leader weakness remains display/risk context pending separate historical validation"
      external_position_boundary:
        requires_external_position_state: true
        no_cny_amounts: true
        no_order_instructions: true
        no_account_cost_or_stop_loss: true
    boundary: "the handoff provides lifecycle, quality gates, data warnings and research context only; all capital, order, entry, exit and risk decisions are outside this strategy"
    source_scope: "unified_25_target_overview_plus_core_and_hk_topic_details"
    action_enum:
      - "observe_only"
      - "candidate_entry"
      - "starter_eligible"
      - "scale_in_eligible"
      - "reduce_to_one_unit"
      - "hold_and_monitor"
      - "de_risk"
    action_mapping:
      effective_consumer_semantics: "all_actions_are_observe_only"
      legacy_action_fields_are_non_operational: true
      de_risk: "maLifecycle.initialStartInvalidated == true OR ((maLifecycle.initialStartActive OR maLifecycle.trendConfirmedActive) AND latest_close < latest_ma60)"
      reduce_to_one_unit: "maLifecycle.trendConfirmedActive AND MA20 profit-protection rule"
      scale_in_eligible: "maLifecycle.trendConfirmedActive AND structure.pass AND breakout.pass AND leader.pass AND entry_data_fresh"
      starter_eligible: "maLifecycle.initialStartActive AND entry_data_fresh"
      candidate_entry: "primary_label == 接近启动 AND latest_close >= latest_ma60 * 0.97 AND entry_data_fresh"
      hold_and_monitor: "primary_label == 趋势延续"
      observe_only: "otherwise"
    entry_priority:
      applies_to_actions:
        - "scale_in_eligible"
        - "starter_eligible"
        - "candidate_entry"
      tie_breakers_in_order:
        - "action_order: scale_in_eligible before starter_eligible before candidate_entry"
        - "stage_pass_count descending"
        - "absorption_rank_pct descending; null treated as 0"
        - "target.order ascending"
    required_target_fields:
      - "action"
      - "actionEventToday"
      - "entryPriorityRank"
      - "signal"
      - "guards"
      - "reasonCodes"
      - "reasons"
      - "positionSignal"

  stage_structure:
    id: "structure"
    title: "低位收敛"
    prerequisites:
      - "low_window.complete_condition"
    pass_formula: "path_a.pass OR path_b.pass"
    warning_formula: "NOT pass AND (path_a.warning OR path_b.warning)"
    path_a:
      metric: "count(close <= ma250 * 0.95 in last 120 trade days)"
      warning_threshold_days: 40
      pass_threshold_days: 60
      intent: "count only effective low-position days and exclude shallow oscillation around ma250"
    path_b:
      metrics:
        below_ma250_days: "count(close < ma250 in last 120 trade days)"
        deep_10_days: "count(close <= ma250 * 0.90 in last 120 trade days)"
      warning_formula: "below_ma250_days >= 24 AND deep_10_days >= 12"
      pass_formula: "below_ma250_days >= 40 AND deep_10_days >= 24"
      intent: "prevent a recent sharp decline from being treated as long-term low-position convergence"
    diagnostic_only:
      metric: "count(close <= ma250 * 0.85 in last 120 trade days)"
      affects_pass: false
      affects_warning: false

  stage_breakout:
    id: "breakout"
    title: "带量突破年线"
    ma60_observation_window:
      gap_formula: "latest_close / latest_ma60 - 1"
      enter_formula: "latest_close >= latest_ma60 * 0.97"
      minimum_gap_percent: -3.0
      role: "required_gate_for_overall_observation_label"
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
      display_value: "last_3_absorption_rank_pct values joined by ' / ' plus qualified_day_count / 3"
    pass_formula: "price_confirmation AND funding_confirmation"
    emerged_formula: "price_confirmation OR funding_confirmation"
    warning_formula: "ma60_observation_window AND NOT pass"
    crowding_risk:
      current_hot_formula: "latest_absorption_rank_pct >= 0.95"
      overheated_formula: "last_3_trade_days_all(absorption_rank_pct >= 0.95)"
      affects_pass: false

  stage_leader:
    id: "leader"
    title: "权重龙头确认"
    signal_role: "industry_state_confirmation_only"
    trade_instruction: false
    chase_leader_stock_allowed: false
    explanation: "strict confirmation is only known after the immediate next market trade day; it confirms industry consensus and must not be interpreted as buying the limit-up leader"
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
      condition: "(structure.pass OR structure.warning) AND breakout.ma60_observation_window"
    - label: "未启动"
      condition: "otherwise"
  side_signal_rule: "when structure is absent or the tracking index is outside the ma60 observation window, breakout and leader signals remain visible but cannot raise the overall label"
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
      selection: "latest_completed_SSE_trade_date"
      before_local_hour_16: "latest_open_SSE_trade_date_before_current_calendar_day"
      at_or_after_local_hour_16: "latest_open_SSE_trade_date_through_current_calendar_day"
      weekend_and_holiday_safe: true
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
        timezone: "Asia/Shanghai"
        crons:
          - "5 21 * * 1-5"
          - "30 22 * * 1-5"
      workflow_dispatch:
        inputs:
          end_date:
            format: "YYYYMMDD"
            required: false
          allow_non_trade_day:
            type: "boolean"
            default: false
          allow_rollback:
            type: "boolean"
            default: false
          rollback_confirmation:
            type: "string"
            required_when: "allow_rollback == true AND end_date < live_latest_date"
            exact_formula: "'ROLLBACK ' + end_date"
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
      target_date_formula: "latest_completed_SSE_trade_date_after_live_latest_date"
      fallback_when_live_date_unavailable: "latest_completed_SSE_trade_date"
      backlog_order: "latest_unpublished_trade_date_first"
      current_day_cutoff: "before_local_hour_16_uses_previous_calendar_day; at_or_after_local_hour_16_uses_current_calendar_day"
      non_trading_day_result: "not_selected_as_target_date"
      target_sources:
        - "industry_insight_sandbox/targets.json"
        - "industry_insight_sandbox/hk_qdii_targets.json"
      target_source_checkout_required: true
      etf_tracking_index_resolution:
        metadata_api: "etf_basic"
        metadata_fields:
          - "ts_code"
          - "index_code"
          - "index_name"
        etf_target_formula: "all targets where kind == etf"
        direct_index_formula: "all targets where kind == index"
        tracking_index_formula: "unique(etf_basic.index_code for every core ETF target) UNION direct index target codes UNION hk_qdii.readinessIndexCode"
        global_index_formula: "unique(hk_qdii.benchmarkCode)"
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
        all_hk_benchmarks:
          api: "index_global"
          codes: "every benchmarkCode from hk_qdii_targets.json"
          minimum_rows: 1
          required_trade_date: "${target_date}"
          missing_any_code_result: "data_ready_false"
      query_control:
        retry_attempts: 3
        retry_backoff_seconds:
          - 2
          - 4
        throttle_seconds_between_symbol_queries: 0.35
      production_short_circuit:
        live_source: "https://raw.githubusercontent.com/keycool/theme_watch/etf-watch-data/overview.json"
        already_current_formula: "live_latest_date >= target_date"
        result:
          already_current: true
          data_ready: false
          reason: "already_current"
          calculate_and_publish: false
        live_check_failure_policy: "continue_to_tushare_readiness"
      polling:
        maximum_attempts: 3
        interval_seconds: 600
        relative_attempt_minutes:
          - 0
          - 10
          - 20
        retry_only_when_reason: "daily_data_incomplete"
        immediate_stop_reasons:
          - "ready"
          - "already_current"
          - "non_trading_day"
      calculate_job_condition: "github.ref == 'refs/heads/main' AND all_probes_ready AND NOT already_current"
    production_concurrency:
      group: "etf-constituent-production"
      cancel_in_progress: false
      maximum_running: 1
    production_date_monotonicity:
      live_source: "https://raw.githubusercontent.com/keycool/theme_watch/etf-watch-data/overview.json"
      live_date_formula: "the single latestDate shared by all live overview targets"
      normal_publish_condition: "candidate_date >= live_date"
      manual_preflight_applies_when: "workflow_dispatch AND end_date is not empty"
      generated_output_guard_applies_before: "vercel_pull"
      rollback_condition: "allow_rollback == true AND rollback_confirmation == 'ROLLBACK ' + candidate_date"
      implicit_rollback_allowed: false
    calculate_and_publish_steps_in_order:
      - "checkout"
      - "setup_python_3_11"
      - "guard_manual_requested_date_if_explicit"
      - "setup_node_22"
      - "restore_market_data_cache"
      - "install_python_dependencies"
      - "npm_ci"
      - "run_unified_etf_and_hk_qdii_workflow"
      - "npm_test_if_calculation_success"
      - "guard_generated_production_date_if_calculation_success"
      - "vercel_pull_production_if_calculation_success"
      - "vercel_build_production_if_calculation_success"
      - "vercel_deploy_production_if_calculation_success"
      - "force_publish_json_to_etf-watch-data_if_calculation_success"
      - "upload_logs_always"
      - "upload_observation_snapshot_if_calculation_success"
      - "send_feishu_webhook_always"
      - "save_market_data_cache_always"

validation:
  offline_backtest:
    decision_use: false
    production_workflow_dependency: false
    lookahead_allowed: false
    default_start_date: "20190101"
    default_end_date: "20260813"
    horizons_trade_days: [5, 20, 60]
    entry_execution_price: "corresponding ETF next market trade date open"
    historical_component_rule: "use latest index weight snapshot not after each decision date"
    current_component_backfill_allowed: false
    current_target_universe_survivorship_bias: true
    true_untouched_out_of_sample_available: false
    event_independence_checks:
      - "same-target non-overlap by horizon"
      - "cross-target market-wave clustering"
    partial_target_rule:
      513970.SH: "price, funding, and moving-average lifecycle only because historical official constituent snapshots are unavailable"
    parameter_writeback_allowed: false
    account_execution_discipline:
      production_decision_use: false
      entry_event: "initial_start_today AND entry_guard_passed"
      entry_execution: "next market trade date ETF open"
      repeated_active_state_can_reenter: false
      automatic_scaling_on_ma250_or_leader: false
      compared_exit_variants:
        - "fixed_20_only"
        - "ma60_exit_only"
        - "fixed_20_or_ma60"
        - "unvalidated_20_or_ma60"
      capacity_grid: [1, 2, 3, 5]
      cost_bps_per_side_grid: [0, 5, 10]
      current_forward_observation_candidate: "fixed_20_only; maximum 3 slots; one third of external satellite capacity per slot"
      candidate_is_production_authorization: false
    expanded_universe_research:
      decision_use: false
      production_workflow_dependency: false
      lookahead_allowed: false
      command: "py -B .\\expanded_universe_research.py --start-date 20120101 --end-date 20260813 --max-indexes 80 --complete-count 30"
      signal_layer_pool_count: 80
      current_target_count_in_pool: 23
      complete_strategy_pool_count: 30
      complete_strategy_data_start_date: "20190101"
      pool_selection: "ETF-backed domestic industry/theme indexes; current targets prioritized; no return-based selection"
      etf_metadata_statuses: ["L", "D", "P"]
      execution_point_in_time_required: true
      wave_cluster_calendar_days: 10
      outputs:
        - "industry_insight_sandbox/backtest_results/etf_watch_expanded_<start>_<end>.json"
        - "industry_insight_sandbox/backtest_results/etf_watch_expanded_<start>_<end>.md"
        - "industry_insight_sandbox/backtest_results/etf_watch_expanded_<start>_<end>_lifecycle_events.csv"
        - "industry_insight_sandbox/backtest_results/etf_watch_expanded_<start>_<end>_waves.csv"
        - "industry_insight_sandbox/backtest_results/etf_watch_expanded_execution_<start>_<end>.json"
      limitations:
        - "signal_layer_uses_index_history_before_etf_listing"
        - "complete_strategy_layer_is_a_30_index_subpool"
        - "current_target_priority_and_metadata_availability_do_not_equal_full_historical_universe"
    outputs:
      - "industry_insight_sandbox/backtest_results/etf_watch_backtest_<start>_<end>.json"
      - "industry_insight_sandbox/backtest_results/etf_watch_backtest_<start>_<end>_events.csv"
      - "industry_insight_sandbox/backtest_results/etf_watch_backtest_<start>_<end>_sensitivity.csv"
      - "industry_insight_sandbox/backtest_results/etf_watch_backtest_<start>_<end>.md"
      - "industry_insight_sandbox/backtest_results/etf_watch_execution_backtest_<start>_<end>.json"
      - "industry_insight_sandbox/backtest_results/etf_watch_execution_backtest_<start>_<end>_summary.csv"
      - "industry_insight_sandbox/backtest_results/etf_watch_execution_backtest_<start>_<end>_trades.csv"
      - "industry_insight_sandbox/backtest_results/etf_watch_execution_backtest_<start>_<end>_nav.csv"
      - "industry_insight_sandbox/backtest_results/etf_watch_execution_backtest_<start>_<end>.md"
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
    target_count: 25
    core_target_count: 23
    hk_qdii_count: 2
    etf_count: 24
    index_count: 1
    overview_codes_equal_unified_target_codes: true
    core_topic_codes_equal_core_target_codes: true
    core_topic_file_slugs_equal_core_target_slugs: true
    every_hk_qdii_output_is_production_integrated: true
    overview_sandbox_flag: true
    every_latest_date_equals_end_date: true
    every_topic_sandbox_flag: true
    every_topic_has_tracking_index_metadata: true
    minimum_chart_rows_per_topic: 250
    minimum_core_components_per_topic: 3
    core_count_equals_component_rows: true
    individual_topic_equals_aggregate_topic: true
    every_component_has_latest_date: true
    every_component_has_boolean_data_fresh: true
    component_latest_date_not_after_topic_as_of: true
    data_fresh_formula: "component.latestDate == topic.meta.latestDate"
    stale_component_can_count_as_active: false
    stale_component_can_count_as_above_ma60: false
    stale_component_can_count_as_above_ma250: false
    stale_component_can_qualify_leader_event: false
    startup_confirmation_requires_fresh_strict_leader: true
    allocation_handoff_target_count: 25
    allocation_handoff_codes_equal_unified_target_codes: true
    allocation_handoff_as_of_equals_end_date: true
    allocation_handoff_execution_owner: "external_monitor"
    allocation_handoff_strategy_executes_orders: false
    allocation_handoff_position_sizing_provided: false
    allocation_handoff_fixed_cny_amount_provided: false
    allocation_handoff_position_signal_requires_external_position_state: true
    allocation_handoff_effective_consumer_mode: "observation_only"
    allocation_handoff_legacy_actions_must_not_trigger_capital: true
    allocation_handoff_target_units_must_be_ignored: true
    stale_component_blocks_position_signal_entry_or_scaling: true
    insufficient_long_cycle_history_blocks_position_signal_entry_or_scaling: true
    stale_weight_blocks_position_signal_entry_or_scaling: true
    leader_confirmation_never_authorizes_leader_stock_chasing: true
    etf_amount_rank_does_not_replace_tracking_index_absorption: true
    signal_followup_decision_use: false
    signal_followup_lookahead_allowed: false
    required_stage_titles_in_order:
      - "低位收敛"
      - "带量突破年线"
      - "权重龙头确认"
  site_test:
    command: "cd industry_insight_sandbox && npm test"
    expected_python_behavior_test_count: 70
    expected_node_render_test_count: 11
    behavior_test_files:
      - "industry_insight_sandbox/tests/test_strategy_behavior.py"
      - "industry_insight_sandbox/tests/test_readiness_behavior.py"
      - "industry_insight_sandbox/tests/test_publication_guards.py"
      - "industry_insight_sandbox/tests/test_moving_average_lifecycle.py"
      - "industry_insight_sandbox/tests/test_backtest_etf_watch.py"
      - "industry_insight_sandbox/tests/test_execution_discipline_backtest.py"
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
      - "same_day_live_overview_short_circuits_readiness"
      - "older_live_overview_does_not_short_circuit_readiness"
      - "weekend_uses_previous_completed_trade_date"
      - "readiness_selects_latest_unpublished_trade_date"
      - "orchestrator_default_date_uses_trade_calendar"
      - "maps_independent_position_stages_without_execution"
      - "ma250_cross_without_all_three_stages_cannot_scale"
      - "entry_ranking_includes_candidate_after_confirmed_and_starter"
      - "history_and_weight_guards_block_entry_without_changing_primary_label"
      - "signal_followup_records_transition_and_available_horizons"
      - "signal_followup_does_not_duplicate_continuing_label"
      - "signal_followup_rejects_date_rollback"
      - "production_date_extracts_single_live_date"
      - "production_date_blocks_implicit_rollback"
      - "production_date_requires_exact_human_confirmation"
      - "production_date_allows_confirmed_rollback"
      - "production_date_allows_same_or_newer_date"
      - "freshness_accepts_excluded_stale_component"
      - "freshness_missing_fields_fail_validation"
      - "freshness_future_component_date_fails_validation"
      - "stale_component_cannot_create_startup_confirmation"
      - "readiness_includes_hk_etfs_tracking_index_and_global_benchmark"
      - "hk_qdii_targets_merge_into_unified_overview"
      - "ma20_rhythm_five_state_boundaries"
      - "ma20_cross_is_warm_up_only"
      - "ma60_cross_with_dynamic_safety_margin_starts_initial_signal"
      - "ma250_cross_confirms_trend_on_same_day"
      - "moving_average_lifecycle_has_no_lookahead"
      - "absolute_five_percent_safety_floor"
      - "backtest_lifecycle_vector_matches_production_engine"
      - "backtest_future_rows_cannot_change_prior_lifecycle_state"
      - "backtest_weight_snapshot_never_uses_future_month"
      - "backtest_executable_return_uses_next_market_open"
      - "backtest_unconditional_baseline_does_not_require_structure_on_sample_day"
      - "execution_backtest_enters_at_next_market_open"
      - "execution_backtest_does_not_reenter_while_held"
      - "execution_backtest_unvalidated_position_exits_after_20_trade_days"
      - "execution_backtest_breakout_validation_extends_until_ma60_failure"
      - "execution_backtest_same_day_capacity_prefers_validated_signal"
  vercel_build_test:
    command: "cd industry_insight_sandbox && npm run build:vercel"
  required_outputs:
    - "industry_insight_sandbox/data/overview.json"
    - "industry_insight_sandbox/data/all_topics.json"
    - "industry_insight_sandbox/data/allocation_handoff.json"
    - "industry_insight_sandbox/data/signal_followup.json"
    - "industry_insight_sandbox/data/topics/<slug>.json"
    - "industry_insight_sandbox/data/hk_qdii/513970-sh.json"
    - "industry_insight_sandbox/data/hk_qdii/513230-sh.json"
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
      - "coreTargetCount"
      - "hkQdiiCount"
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
      - "rhythmLabel"
      - "maLifecycleLabel"
      - "maSafetyMarginPassed"
      - "maSeparationPct"
      - "maSeparationRankPct"
      - "initialStartToday"
      - "trendConfirmedToday"
      - "capitalInterface"
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
      - "route"
    core_target_additional_required_fields:
      - "belowMa250FiveDays"
      - "ma60Near"
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
    required_summary_fields:
      - "label"
      - "rhythmLabel"
      - "maLifecycle"
    ma_lifecycle_required_fields:
      - "label"
      - "separationPct"
      - "separationRankPct"
      - "dynamicThresholdPct"
      - "separationObservationCount"
      - "safetyMarginPassed"
      - "convergenceDays"
      - "deathCrossDate"
      - "warmUpDate"
      - "initialStartDate"
      - "trendConfirmedDate"
      - "initialStartToday"
      - "trendConfirmedToday"
      - "initialStartActive"
      - "trendConfirmedActive"
      - "initialStartInvalidated"
      - "capitalInterface"
      - "executionOwner"
      - "strategyExecutesOrders"
    chart_required_fields:
      - "date"
      - "close"
      - "ma20"
      - "ma60"
      - "ma250"
    core_topic_summary_additional_required_fields:
      - "belowMa250FiveDays"
      - "ma60Near"
  allocation_handoff:
    path: "industry_insight_sandbox/data/allocation_handoff.json"
    required_meta_fields:
      - "schemaVersion"
      - "generatedAt"
      - "asOf"
      - "targetCount"
      - "executionOwner"
      - "strategyExecutesOrders"
      - "positionSizingProvided"
      - "allocationMode"
      - "allocationUnitOwner"
      - "fixedCnyAmountProvided"
    required_target_fields:
      - "code"
      - "asOf"
      - "action"
      - "actionEventToday"
      - "entryPriorityRank"
      - "targetAllocationUnits"
      - "allocationInstruction"
      - "positionSignal"
      - "primaryLabel"
      - "lifecycleLabel"
      - "signal"
      - "guards"
      - "reasonCodes"
      - "reasons"
    position_signal_required_fields:
      - "stage"
      - "referenceUnits"
      - "newEntryAllowed"
      - "addPositionAllowed"
      - "entryAction"
      - "riskAction"
      - "reasonCodes"
      - "riskReasonCodes"
      - "requiresExternalPositionState"
      - "leaderConfirmationRole"
      - "leaderStockChaseAllowed"
      - "executionOwner"
  signal_followup:
    path: "industry_insight_sandbox/data/signal_followup.json"
    schema_version: "1.0"
    decision_use: false
    lookahead_allowed: false
    tracked_signal: "启动确认 transition only"
    horizons_trade_days: [5, 20, 60]
    benchmark_by_engine:
      core_a_share: "000300.SH"
      hk_qdii: "each topic's declared benchmark, currently HSI"
    persistence_source: "published etf-watch-data branch restored before each production calculation"

publication:
  live_data:
    repository: "keycool/theme_watch"
    branch: "etf-watch-data"
    update_mode: "force_push_generated_json_only"
    files:
      - "overview.json"
      - "all_topics.json"
      - "allocation_handoff.json"
      - "signal_followup.json"
      - "topics/**"
      - "hk_qdii/**"
  web_application:
    provider: "Vercel"
    project_name: "etf-core-constituent-watch"
    root_directory: "industry_insight_sandbox"
    production_url: "https://etf-core-constituent-watch.vercel.app"
    framework: "Next.js"
    build_command: "npm run build:vercel"
    client_data_source: "https://raw.githubusercontent.com/keycool/theme_watch/etf-watch-data/overview.json"
    live_fetch_cache: "no-store"
    live_data_accept_condition: "meta.targetCount == 25 AND meta.hkQdiiCount == 2"
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
    - "github_ref_is_not_refs_heads_main"
    - "candidate_date_older_than_live_without_confirmed_rollback"
    - "generator_exit_code_nonzero"
    - "generated_data_validation_failed"
    - "npm_test_failed"
    - "vercel_pull_failed"
    - "vercel_build_failed"
    - "vercel_deploy_failed"
  publication_order_invariant: "main_ref_and_date_guard_and_vercel_pull_and_build_and_deploy_success_before_etf_watch_data_force_push"
  preserve_and_upload_logs_on_failure: true
  send_feishu_on_failure: true
  save_cache_on_failure: true
  error_codes:
    missing_tushare_token: "TUSHARE_TOKEN_MISSING"
    non_trade_day: "SKIPPED_NON_TRADE_DAY"
    scheduled_data_incomplete: "TUSHARE_DAILY_DATA_NOT_READY"
    non_main_production_ref: "PRODUCTION_REF_NOT_MAIN"
    production_date_rollback_blocked: "PRODUCTION_DATE_ROLLBACK_BLOCKED"
    rollback_confirmation_invalid: "ROLLBACK_CONFIRMATION_INVALID"
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
    - "update industry_insight_sandbox/hk_qdii_targets.json when changing HK targets"
    - "update expected target counts in run_etf_constituent_workflow.py and tests"
    - "update this SOP invariants"
  prohibited_behavior:
    - "silently infer a replacement threshold"
    - "silently use SW L2 to determine labels"
    - "publish when validation status is failed"
    - "log secret values"
---

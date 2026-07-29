# HK QDII Watch Machine SOP

```yaml
contract:
  id: hk_qdii_watch
  version: 2.0.0
  mode: production_extension
  production_integrated: true
  unified_overview_target_count: 23
  target_count: 2
  targets:
    - code: 513970.SH
      related_fund: null
      name: 恒生消费ETF
      route: /hk-qdii/513970-sh
      output: data/hk_qdii/513970-sh.json
      structure_source: etf_price_proxy
    - code: 513230.SH
      related_fund: 017832.OF
      name: 港股通消费ETF
      route: /hk-qdii/513230-sh
      output: data/hk_qdii/513230-sh.json
      structure_source: tracking_index
  integration:
    target_source: hk_qdii_targets.json
    overview_merger: merge_hk_qdii_overview.py
    overview_output: data/overview.json
    local_orchestrator: ../run_etf_constituent_workflow.py
    ci_orchestrator: ../.github/workflows/etf-constituent-daily.yml
    live_data_directory: hk_qdii

source_contract:
  target_513970:
    etf_daily:
      provider: Tushare
      endpoint: fund_daily
      code: 513970.SH
      required_fields: [trade_date, close, pct_chg, amount]
    constituents:
      provider: Hang Seng Indexes Company
      endpoint: constituents/v1
      index_code: "02018.00"
      expected_count: 10
      fields: [stockCode, stockName, weightOrder, tradeDate]
      warning: API提供官方排序，不提供权重百分比
  target_513230:
    etf_daily:
      provider: Tushare
      endpoint: fund_daily
      code: 513230.SH
    feeder_nav:
      provider: Tushare
      endpoint: fund_nav
      code: 017832.OF
      role: display_only
    tracking_index_daily:
      provider: Tushare
      endpoint: index_daily
      code: 931454.CSI
      required_fields: [trade_date, close, pct_chg, amount]
    tracking_index_weights:
      provider: Tushare
      endpoint: index_weight
      code: 931454.CSI
      expected_count: 50
      selected_snapshot: max(trade_date <= requested_end_date)
      leader_universe: top_10_by_weight
  benchmark_daily:
    provider: Tushare
    endpoint: index_global
    code: HSI
    required_fields: [trade_date, close]
  constituent_daily:
    provider: Tencent Securities
    endpoint: fqkline/get
    adjustment: qfq
    expected_count: 10

freshness:
  as_of: min(ETF最新日, 判断对象最新日, HSI最新日)
  requirements:
    - 每只成分必须输出latestDate
    - 每只成分必须输出布尔dataFresh
    - latestDate不得晚于as_of
    - dataFresh=false的成分不得参与龙头确认或群体广度
    - 缺少字段或不足250条成分日线时生成失败

strategy:
  stage_1:
    name: 低位收敛
    object_by_target:
      513970.SH: 513970 ETF价格代理
      513230.SH: 931454.CSI跟踪指数
    window: 120
    pass_if_any:
      - count(close < MA250) >= 60
      - count(close <= MA250 * 0.90) >= 24
    warning_if_any:
      - count(close < MA250) >= 40
      - count(close <= MA250 * 0.90) >= 12
    display_only:
      - count(close <= MA250 * 0.85)
  stage_2:
    name: 量价趋势确认
    object_by_target:
      513970.SH: 513970 ETF
      513230.SH: 931454.CSI跟踪指数
    early_warning:
      - close > MA60
    price_confirm:
      - latest_close > latest_MA250
      - previous_close > previous_MA250
    funding_confirm:
      metric_by_target:
        513970.SH: ETF成交额自身252日历史分位
        513230.SH: 跟踪指数成交额自身252日历史分位
      rule: latest_3_days_each >= 0.80
    crowding_warning:
      rule: latest_percentile >= 0.95
    pass: price_confirm AND funding_confirm
  stage_3:
    name: 港股权重龙头确认
    official_universe: 恒生消费官方前十大成分
    official_universe_by_target:
      513970.SH: 恒生指数公司公开前十大排序
      513230.SH: 中证指数月度权重前十大
    strict_group: rank_1_to_3
    warning_group: rank_4_to_10
    event:
      absolute_return: daily_pct >= 5.0
      relative_return: daily_pct >= prior_120_day_return_p95
      strict_window: latest_5_market_days
      warning_window: latest_3_market_days
      continuation:
        - next_trading_day_pct > 0
        - latest_close >= event_day_close
        - dataFresh == true
    breadth:
      freshness_gate: top10_dataFresh_count == 10
      rules:
        - count(top10 close > MA60) >= 5
        - count(top10 5_day_return > 0) >= 5
    pass: strict_event_qualified AND breadth
    warning: secondary_event_qualified OR breadth
    explicit_exclusion: 不使用A股涨停阈值

label:
  启动确认: three_stages_passed
  接近启动: stage_1_passed AND stage_2_passed AND stage_3_warning
  观察中: any_stage_passed_or_warning
  未启动: no_stage_passed_or_warning

execution:
  unified_command:
    - py -B ../run_etf_constituent_workflow.py --end-date YYYYMMDD --trigger-type manual
  commands:
    - uv run --with tushare python generate_hk_qdii_dashboard_data.py --end-date YYYYMMDD
    - uv run --with tushare python generate_hk_connect_consumer_dashboard_data.py --end-date YYYYMMDD
  environment:
    required: [TUSHARE_TOKEN]
  validation:
    - python -m unittest tests.test_hk_qdii_behavior
    - npm test
    - npm run lint
    - npm run build:vercel
```

## Machine invariants

- This contract extends the 20-target A-share core into one 22-target production overview.
- Keep HK calculation engines separate from the A-share generator; unify only at orchestration, overview, validation and publication layers.
- Treat 017832.OF as a feeder display identity; calculate its strategy from 513230.SH and 931454.CSI.
- Never interpret ETF proxy values as official Hang Seng Consumption Index points.
- Never interpret `weightOrder` as a weight percentage.
- For 513230.SH, use official `index_weight` values and never replace them with market-cap guesses.
- Never use a rank 4-10 event as strict leader confirmation.
- Never allow a stale constituent to confirm an event or breadth.
- Both HK outputs must set `meta.productionIntegrated=true` before overview merge or publication.
- Publish `data/hk_qdii/**` only after the same main-branch, date monotonicity, test and Vercel guards used by the core workflow pass.

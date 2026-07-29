# AI Project SOP

## First Read Rule

任何AI代理接手本仓库时，必须先完整读取本文件，再读取其他项目文件或修改代码。

本文件负责项目级路由与发布底线；策略阈值、输出结构和具体执行顺序以对应机器SOP为准。

## Machine Router

```yaml
project:
  id: theme_watch
  default_branch: main
  repository: keycool/theme_watch
  current_release: etf-watch-v2.1.0

systems:
  etf_constituent_watch:
    status: primary_scheduled_production
    description: 22标的ETF、指数与港股QDII核心成分启动观察
    read_order:
      - industry_insight_sandbox/ETF_CONSTITUENT_WATCH_MACHINE_SOP.md
      - industry_insight_sandbox/README.md
    hk_qdii_extra_read:
      when: task涉及513970.SH、513230.SH、017832.OF或港股QDII
      file: industry_insight_sandbox/HK_QDII_WATCH_MACHINE_SOP.md
    target_sources:
      core_20: industry_insight_sandbox/targets.json
      hk_qdii_2: industry_insight_sandbox/hk_qdii_targets.json
    local_orchestrator: run_etf_constituent_workflow.py
    ci_orchestrator: .github/workflows/etf-constituent-daily.yml
    schedule:
      timezone: Asia/Shanghai
      cron: "25 22 * * 1-5"
    production_url: https://etf-core-constituent-watch.vercel.app
    live_data_branch: etf-watch-data

  legacy_theme_watch:
    status: manual_only
    description: 申万二级扫描、静态报告与GitHub Pages历史链路
    read_order:
      - reports/theme_watch/theme_watch_sop.md
      - reports/theme_watch/daily_update_runbook.md
    local_orchestrator: run_theme_watch_workflow.py
    ci_orchestrator: .github/workflows/theme-watch-daily.yml
    scheduled: false

mandatory_invariants:
  production_branch: refs/heads/main
  preserve_user_worktree: true
  secrets_must_not_be_logged_or_committed: true
  etf_and_legacy_cache_must_not_mix: true
  etf_unified_target_count: 22
  etf_core_target_count: 20
  hk_qdii_target_count: 2
  publish_date_must_not_regress_without_explicit_confirmation: true
  vercel_success_required_before_live_data_publish: true
  stale_component_cannot_confirm_leader_or_group_strength: true

change_routing:
  strategy_threshold:
    update:
      - implementation
      - behavior_tests
      - corresponding_machine_sop
  target_universe:
    update:
      - authoritative_target_json
      - orchestrator_validation
      - rendered_page_tests
      - corresponding_machine_sop
  workflow_or_publication:
    update:
      - github_actions_workflow
      - publication_tests
      - corresponding_machine_sop
    parse_yaml_after_change: true
```

## ETF Production Execution

统一ETF生产链路的固定顺序是：

1. 检查线上是否已经包含目标日期。
2. 检查20个核心目标、2个港股ETF、可用真实跟踪指数和恒生基准是否就绪。
3. 运行20目标核心生成器。
4. 分别运行513970与513230港股专用生成器。
5. 合并为22标的统一总览。
6. 校验目标数量、日期、新鲜度、标签闭环和输出文件。
7. 运行Python测试、页面测试、lint与Vercel构建。
8. 检查生产日期不得隐式回退。
9. 部署Vercel Production。
10. Vercel成功后才覆盖`etf-watch-data`分支。
11. 上传日志与快照并发送飞书摘要。

港股计算器不得被合并进A股生成器：

- 513970使用ETF价格代理、ETF成交活跃度与恒生消费官方前十大。
- 017832只作为联接基金展示身份；策略下沉到513230及931454.CSI。
- 港股龙头事件不得套用A股涨停阈值。

## Required Verification

ETF相关代码、数据、页面、工作流或文档变更完成后，至少执行：

```powershell
cd "D:\CC\Industry Insight\industry_insight_sandbox"
python -m unittest discover -s tests -p "test_*.py"
npm run lint
npm test
npm run build:vercel
```

工作流或机器SOP发生变化时，还必须：

- 解析GitHub Actions YAML。
- 解析机器SOP YAML。
- 验证`overview.json`恰有22个标的且日期唯一。
- 验证所有总览行都具有可访问路由。
- 验证候选生产日期不早于线上日期。

## Git and Handoff

- 默认分支为`main`。
- 未经用户明确要求，不提交、不推送、不部署。
- 用户明确要求提交时，只暂存任务范围内文件，避免夹带无关工作树修改。
- 推送后核对远端SHA和GitHub Actions状态；远端运行失败时保留证据，不得声称发布成功。
- 当前版本、运行方式和架构事实写入README或机器SOP，不把临时会话记录追加到入口文档。

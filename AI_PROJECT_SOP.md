# AI Project SOP

## First Read Rule

Any AI agent taking over this project must read this file before reading other project documents or modifying code.

For ETF/index core constituent observation tasks, the next mandatory file is
`industry_insight_sandbox/ETF_CONSTITUENT_WATCH_MACHINE_SOP.md`. Treat its
YAML frontmatter as the machine execution contract and halt on implementation
drift.

## Machine SOP

```yaml
meta:
  sop_id: "theme_watch_workflow_data_integrity_v1"
  version: "1.0.0"
  audience: "ai_agent_only"
  project: "${project_name}"
  default_branch: "${default_branch}"
  required_vars:
    - "${project_root}"
    - "${repo_owner}"
    - "${repo_name}"
    - "${default_branch}"
    - "${pages_url}"
    - "${run_date}"
  invariant:
    strategy_core_logic_mutation_allowed: false
    publish_branch_must_equal_default_branch: true

triggers:
  - trigger_id: "remote_data_insufficient"
    event: "github_pages_validation"
    condition: "${published_page_bad_count} > 0"
  - trigger_id: "workflow_after_push"
    event: "git_push"
    condition: "${pushed_branch} == ${default_branch}"
  - trigger_id: "phase_archive"
    event: "weekly_review_or_version_archive"
    condition: "${stage_status} == 'ready_for_archive'"

steps:
  - step_id: "verify_default_branch"
    action:
      tool: "shell"
      args:
        cwd: "${project_root}"
        command: "git branch --show-current && git remote show origin"
    outputs:
      current_branch: "string"
      default_branch: "string"
      branch_aligned: "boolean"
    condition: "${current_branch} == ${default_branch}"
    on_failure:
      status: "failed"
      error_code: "BRANCH_NOT_DEFAULT"
      next_step: "switch_to_default_branch"

  - step_id: "switch_to_default_branch"
    action:
      tool: "shell"
      args:
        cwd: "${project_root}"
        command: "git fetch origin ${default_branch} && git switch -c ${work_branch} origin/${default_branch}"
    outputs:
      work_branch: "string"
      base_sha: "string"
    condition: "${branch_aligned} == false"
    on_failure:
      status: "failed"
      error_code: "DEFAULT_BRANCH_SWITCH_FAILED"
      notify: "agent_name"

  - step_id: "verify_workflow_push_trigger"
    action:
      tool: "file_check"
      args:
        path: "${project_root}/.github/workflows/theme-watch-daily.yml"
        yaml_path: "on.push.branches"
        expected_value:
          - "${default_branch}"
    outputs:
      workflow_push_trigger_present: "boolean"
    condition: "${workflow_push_trigger_present} == true"
    on_failure:
      status: "failed"
      error_code: "MISSING_PUSH_TRIGGER"
      next_step: "patch_workflow_push_trigger"

  - step_id: "patch_workflow_push_trigger"
    action:
      tool: "file_patch"
      args:
        path: "${project_root}/.github/workflows/theme-watch-daily.yml"
        yaml_path: "on.push.branches"
        value:
          - "${default_branch}"
    outputs:
      workflow_file_changed: "boolean"
    condition: "${workflow_push_trigger_present} == false"
    on_failure:
      status: "failed"
      error_code: "PUSH_TRIGGER_PATCH_FAILED"
      notify: "agent_name"

  - step_id: "verify_committed_cache_seed_restore"
    action:
      tool: "file_check"
      args:
        path: "${project_root}/.github/workflows/theme-watch-daily.yml"
        required_step_name: "Restore committed cache seeds"
        required_seed_files:
          - "${project_root}/.cache_scan_v2/sw_index_classify.csv"
          - "${project_root}/.cache_scan_v2/sw_daily_full_history.csv"
          - "${project_root}/.cache_scan_v2/daily_market_amount_history.csv"
    outputs:
      cache_seed_restore_present: "boolean"
    condition: "${cache_seed_restore_present} == true"
    on_failure:
      status: "failed"
      error_code: "MISSING_CACHE_SEED_RESTORE"
      next_step: "patch_cache_seed_restore"

  - step_id: "patch_cache_seed_restore"
    action:
      tool: "file_patch"
      args:
        path: "${project_root}/.github/workflows/theme-watch-daily.yml"
        insert_after_step: "Restore cache"
        step:
          name: "Restore committed cache seeds"
          run:
            - "git checkout -- .cache_scan_v2/sw_index_classify.csv"
            - "git checkout -- .cache_scan_v2/sw_daily_full_history.csv"
            - "git checkout -- .cache_scan_v2/daily_market_amount_history.csv"
    outputs:
      workflow_file_changed: "boolean"
    condition: "${cache_seed_restore_present} == false"
    on_failure:
      status: "failed"
      error_code: "CACHE_SEED_RESTORE_PATCH_FAILED"
      notify: "agent_name"

  - step_id: "verify_market_amount_seed"
    action:
      tool: "csv_check"
      args:
        path: "${project_root}/.cache_scan_v2/daily_market_amount_history.csv"
        required_columns:
          - "trade_date"
          - "market_amount"
        min_rows: 250
    outputs:
      seed_rows: "integer"
      seed_min_date: "string:YYYYMMDD"
      seed_max_date: "string:YYYYMMDD"
    condition: "${seed_rows} >= 250"
    on_failure:
      status: "failed"
      error_code: "MARKET_AMOUNT_SEED_INSUFFICIENT"
      next_step: "generate_market_amount_seed"

  - step_id: "generate_market_amount_seed"
    action:
      tool: "python"
      args:
        cwd: "${project_root}"
        script: "build_market_amount_seed_from_daily_market_cache"
        input_glob: "${project_root}/.cache_scan_v2/daily_market_*.csv"
        output_csv: "${project_root}/.cache_scan_v2/daily_market_amount_history.csv"
    outputs:
      seed_rows: "integer"
      seed_output_csv: "string"
    condition: "${seed_rows} >= 250"
    on_failure:
      status: "failed"
      error_code: "MARKET_AMOUNT_SEED_GENERATION_FAILED"
      notify: "agent_name"

  - step_id: "verify_gitignore_cache_rules"
    action:
      tool: "file_check"
      args:
        path: "${project_root}/.gitignore"
        required_lines:
          - ".cache_scan_v2/*"
          - "!.cache_scan_v2/"
          - "!.cache_scan_v2/sw_index_classify.csv"
          - "!.cache_scan_v2/sw_daily_full_history.csv"
          - "!.cache_scan_v2/daily_market_amount_history.csv"
    outputs:
      gitignore_seed_rules_present: "boolean"
    condition: "${gitignore_seed_rules_present} == true"
    on_failure:
      status: "failed"
      error_code: "GITIGNORE_CACHE_RULES_INVALID"
      notify: "agent_name"

  - step_id: "verify_market_amount_loader"
    action:
      tool: "file_check"
      args:
        path: "${project_root}/run_sw_l2_strategy_scan.py"
        required_symbols:
          - "MARKET_AMOUNT_HISTORY_PATH"
          - "_load_market_amount_seed"
          - "_save_market_amount_seed"
    outputs:
      market_amount_seed_loader_present: "boolean"
    condition: "${market_amount_seed_loader_present} == true"
    on_failure:
      status: "failed"
      error_code: "MARKET_AMOUNT_LOADER_MISSING"
      notify: "agent_name"

  - step_id: "verify_report_validator_guards"
    action:
      tool: "file_check"
      args:
        path: "${project_root}/theme_watch_validate_reports.py"
        required_checks:
          - "data-insufficient badge"
          - "empty chart text"
          - "Scan CSV has data-insufficient crowding rows"
    outputs:
      validation_guards_present: "boolean"
    condition: "${validation_guards_present} == true"
    on_failure:
      status: "failed"
      error_code: "VALIDATION_GUARDS_MISSING"
      notify: "agent_name"

  - step_id: "run_local_workflow"
    action:
      tool: "shell"
      args:
        cwd: "${project_root}"
        command: "py -B ./run_theme_watch_workflow.py --end-date ${run_date} --trigger-type manual --skip-sync"
        timeout_seconds: 240
    outputs:
      workflow_exit_code: "integer"
      workflow_status: "enum:success|warning|failed|skipped"
      workflow_issues_count: "integer"
      workflow_summary_json: "string"
    condition: "${workflow_exit_code} == 0 && ${workflow_status} == 'success' && ${workflow_issues_count} == 0"
    on_failure:
      status: "failed"
      error_code: "LOCAL_WORKFLOW_FAILED"
      notify: "agent_name"

  - step_id: "verify_local_outputs"
    action:
      tool: "python"
      args:
        cwd: "${project_root}"
        script: "verify_theme_watch_outputs"
        scan_csv: "${project_root}/sw_l2_strategy_scan.csv"
        pages_dir: "${project_root}/reports/theme_watch/pages"
        correlations_dir: "${project_root}/reports/theme_watch/correlations"
        expected_run_date: "${run_date}"
        forbidden_page_markers:
          - ">数据不足<"
          - "历史数据不足"
          - "暂时无法绘图"
          - "暂无法画图"
    outputs:
      scan_latest_date: "string:YYYYMMDD"
      crowding_data_insufficient_rows: "integer"
      bad_page_count: "integer"
      bad_correlation_count: "integer"
      total_svg_count: "integer"
    condition: "${scan_latest_date} == ${run_date} && ${crowding_data_insufficient_rows} == 0 && ${bad_page_count} == 0 && ${bad_correlation_count} == 0 && ${total_svg_count} >= 19"
    on_failure:
      status: "failed"
      error_code: "LOCAL_OUTPUT_VERIFICATION_FAILED"
      notify: "agent_name"

  - step_id: "commit_and_push"
    action:
      tool: "shell"
      args:
        cwd: "${project_root}"
        command: "git add -A && git commit -m ${commit_message} && git push origin HEAD:${default_branch}"
    outputs:
      commit_sha: "string"
      pushed_branch: "string"
      pushed_sha: "string"
    condition: "${pushed_branch} == ${default_branch}"
    on_failure:
      status: "failed"
      error_code: "COMMIT_OR_PUSH_FAILED"
      notify: "agent_name"

  - step_id: "wait_for_github_actions"
    action:
      tool: "github_api"
      args:
        repo: "${repo_owner}/${repo_name}"
        endpoint: "/actions/runs"
        poll_interval_seconds: 15
        max_polls: 30
        match:
          head_sha: "${pushed_sha}"
          branch: "${default_branch}"
    outputs:
      run_id: "string"
      run_status: "string"
      run_conclusion: "string"
      run_url: "string"
    condition: "${run_status} == 'completed' && ${run_conclusion} == 'success'"
    on_failure:
      status: "failed"
      error_code: "REMOTE_WORKFLOW_FAILED"
      notify: "agent_name"

  - step_id: "verify_published_pages"
    action:
      tool: "python"
      args:
        cwd: "${project_root}"
        script: "fetch_and_verify_published_theme_pages"
        pages_url: "${pages_url}"
        expected_page_count: 19
        min_total_svg_count: 19
        forbidden_markers:
          - ">数据不足<"
          - "历史数据不足"
          - "暂时无法绘图"
          - "暂无法画图"
    outputs:
      checked_pages: "integer"
      total_svg_count: "integer"
      bad_pages: "array<string>"
      published_page_bad_count: "integer"
    condition: "${checked_pages} == 19 && ${total_svg_count} >= 19 && ${published_page_bad_count} == 0"
    on_failure:
      status: "failed"
      error_code: "PUBLISHED_PAGE_VERIFICATION_FAILED"
      notify: "agent_name"

handoff_contract:
  producer_agent: "technical_coordination_agent"
  consumer_agent: "next_execution_agent"
  payload_format: "yaml"
  required_fields:
    project_root:
      type: "string"
      format: "path"
      value: "${project_root}"
    repo:
      type: "string"
      format: "owner/name"
      value: "${repo_owner}/${repo_name}"
    default_branch:
      type: "string"
      value: "${default_branch}"
    run_date:
      type: "string"
      format: "YYYYMMDD"
      value: "${run_date}"
    latest_successful_commit:
      type: "string"
      format: "git_sha"
      value: "${pushed_sha}"
    latest_successful_actions_run_id:
      type: "string"
      value: "${run_id}"
    latest_successful_actions_run_url:
      type: "string"
      format: "url"
      value: "${run_url}"
    pages_url:
      type: "string"
      format: "url"
      value: "${pages_url}"
    cache_seed_files:
      type: "array<string>"
      value:
        - "${project_root}/.cache_scan_v2/sw_index_classify.csv"
        - "${project_root}/.cache_scan_v2/sw_daily_full_history.csv"
        - "${project_root}/.cache_scan_v2/daily_market_amount_history.csv"
    validation_result:
      type: "object"
      schema:
        checked_pages: "integer"
        total_svg_count: "integer"
        published_page_bad_count: "integer"
        bad_pages: "array<string>"
    failure_escalation:
      type: "object"
      schema:
        notify: "agent_name"
        required_evidence:
          - "run_id"
          - "run_url"
          - "failed_step_id"
          - "error_code"
          - "stdout_log_path"
```

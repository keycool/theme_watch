# AI Project SOP

## Load Order

1. Read this file first.
2. Parse the YAML block only.
3. Use `reports/theme_watch/` as the current theme-watch output root.
4. Treat `reports/theme_watch/theme_watch_sop.md` and `reports/theme_watch/daily_update_runbook.md` as secondary references.

## SOP

```yaml
meta:
  sop_id: theme_watch_phase_archive_v1
  objective: phase_summary_to_machine_readable_archive
  project: theme_watch
  stage: weekly_retro_and_version_archive
  execution_mode: deterministic
  assumptions:
    - source_repo_root: ${project_root}
    - carrier_repo_root: ${project_root}
    - summary_source: ${phase_summary_markdown}
    - workflow_name: ${workflow_name}
    - branch_name: ${branch_name}
    - archive_date: ${archive_date}
  success_criteria:
    - ${project_root}/.github/workflows/${workflow_name}.yml exists
    - ${project_root}/theme_watch_preflight.py exists
    - ${project_root}/theme_watch_validate_reports.py exists
    - ${project_root}/theme_watch_feishu_webhook.py exists
    - latest_github_actions_run.conclusion == success
    - latest_github_actions_run.jobs.update == success
    - latest_github_actions_run.jobs.deploy == success
    - latest_github_actions_run.jobs.notify == success
    - latest_github_actions_run.jobs.verify_pages == success
  known_constraints:
    - base_sync_mode: disabled
    - feishu_notification_mode: webhook_only
    - report_validation_mode: structural
    - homepage_link_validation_mode: non_brittle
  variables:
    project_root: ${project_root}
    workflow_file: ${project_root}/.github/workflows/${workflow_name}.yml
    summary_dir: ${project_root}/logs/theme_watch_workflow
    report_root: ${project_root}/reports/theme_watch
    pages_root: ${project_root}/reports/theme_watch/pages
    homepage_file: ${project_root}/reports/theme_watch/index.html
    topic_pages_config: ${project_root}/theme_watch_config.py
    preflight_script: ${project_root}/theme_watch_preflight.py
    validate_script: ${project_root}/theme_watch_validate_reports.py
    webhook_script: ${project_root}/theme_watch_feishu_webhook.py
    workflow_entry_script: ${project_root}/run_theme_watch_workflow.py

triggers:
  - trigger_id: phase_close_manual
    type: manual
    condition: ${phase_status} == "closing"
  - trigger_id: workflow_repeated_failure
    type: event
    condition: ${github_actions_failure_count_24h} >= 2
  - trigger_id: release_archive
    type: schedule
    condition: ${weekday} == "Sunday" and ${hour_24} == 20
  - trigger_id: handoff_required
    type: event
    condition: ${next_agent_name} != ""

steps:
  - step_id: collect_phase_state
    condition: ${phase_summary_markdown} != ""
    action:
      tool: shell_command
      args:
        command: Get-ChildItem -Force ${project_root}
    outputs:
      repo_listing: text
    on_failure:
      action:
        tool: shell_command
        args:
          command: git -C ${project_root} rev-parse --show-toplevel
      outputs:
        fallback_repo_root: text
      result: blocked_missing_repo_context

  - step_id: normalize_phase_facts
    condition: ${phase_summary_markdown} != ""
    action:
      tool: shell_command
      args:
        command: py -c "import json; print(json.dumps({'migration_target':'github_actions','notification_target':'feishu_webhook','base_sync_enabled':False,'preflight_enabled':True,'structural_validation_enabled':True,'verify_pages_checkout_required':True,'verify_pages_retry_enabled':True}, ensure_ascii=False))"
    outputs:
      normalized_phase_facts: json
    on_failure:
      action:
        tool: shell_command
        args:
          command: Write-Output '{"migration_target":"github_actions","notification_target":"feishu_webhook","base_sync_enabled":false,"preflight_enabled":true,"structural_validation_enabled":true,"verify_pages_checkout_required":true,"verify_pages_retry_enabled":true}'
      outputs:
        normalized_phase_facts: json
      result: normalization_failed

  - step_id: verify_required_files
    condition: ${project_root} != ""
    action:
      tool: shell_command
      args:
        command: py -c "from pathlib import Path; import json; import sys; root=Path(r'${project_root}'); files={'workflow_file':root/'.github/workflows/${workflow_name}.yml','preflight_script':root/'theme_watch_preflight.py','validate_script':root/'theme_watch_validate_reports.py','webhook_script':root/'theme_watch_feishu_webhook.py','workflow_entry_script':root/'run_theme_watch_workflow.py'}; result={k:v.exists() for k,v in files.items()}; missing=[k for k,ok in result.items() if not ok]; print(json.dumps({'exists':result,'missing':missing}, ensure_ascii=False)); sys.exit(1 if missing else 0)"
    outputs:
      required_files_check: json
    on_failure:
      action:
        tool: shell_command
        args:
          command: Write-Output '{"result":"missing_required_files"}'
      outputs:
        required_files_check: json
      result: blocked_missing_required_files

  - step_id: run_local_preflight
    condition: ${run_preflight} == true
    action:
      tool: shell_command
      args:
        command: py ${project_root}/theme_watch_preflight.py --end-date ${archive_date_compact}
        workdir: ${project_root}
        timeout_ms: 1200000
    outputs:
      preflight_stdout: text
      preflight_exit_code: integer
    on_failure:
      action:
        tool: shell_command
        args:
          command: py ${project_root}/theme_watch_validate_reports.py
          workdir: ${project_root}
          timeout_ms: 600000
      outputs:
        fallback_validation_stdout: text
        fallback_validation_exit_code: integer
      result: local_preflight_failed

  - step_id: inspect_validation_logic
    condition: ${inspect_validation_logic} == true
    action:
      tool: shell_command
      args:
        command: py -c "from pathlib import Path; import json; s=Path(r'${project_root}/theme_watch_validate_reports.py').read_text(encoding='utf-8', errors='replace'); facts={'has_homepage_overview_table_check':'<table class=\"overview-table\">' in s,'has_target_link_check':'class=\"target-link\"' in s,'has_topic_page_structure_check':'sparkline' in s,'has_brittle_homepage_href_assert':'Homepage missing topic link' in s}; print(json.dumps(facts, ensure_ascii=False))"
    outputs:
      validation_logic_facts: json
    on_failure:
      action:
        tool: shell_command
        args:
          command: Write-Output '{"result":"validation_logic_unreadable"}'
      outputs:
        validation_logic_facts: json
      result: inspection_failed

  - step_id: confirm_latest_actions_status
    condition: ${latest_run_payload_json} != ""
    action:
      tool: shell_command
      args:
        command: py -c "import json, os, sys; payload=json.loads(os.environ['LATEST_RUN_PAYLOAD_JSON']); jobs=payload['jobs']; ok=(payload['conclusion']=='success' and jobs.get('update')=='success' and jobs.get('deploy')=='success' and jobs.get('notify')=='success' and jobs.get('verify_pages')=='success'); print(json.dumps(payload, ensure_ascii=False)); sys.exit(0 if ok else 1)"
    outputs:
      latest_run_status: json
    on_failure:
      action:
        tool: shell_command
        args:
          command: Write-Output '{"result":"latest_run_not_success"}'
      outputs:
        latest_run_status: json
      result: blocked_latest_run_failed

  - step_id: archive_phase_summary
    condition: ${archive_enabled} == true
    action:
      tool: shell_command
      args:
        command: New-Item -ItemType Directory -Force ${project_root}/archive/${archive_date}
    outputs:
      archive_dir: path
    on_failure:
      action:
        tool: shell_command
        args:
          command: Write-Output '{"result":"archive_write_failed"}'
      outputs:
        archive_result: json
      result: archive_failed

  - step_id: emit_handoff_payload
    condition: ${next_agent_name} != ""
    action:
      tool: shell_command
      args:
        command: py -c "import json; payload={'next_agent_name':'${next_agent_name}','workflow_file':'${project_root}/.github/workflows/${workflow_name}.yml','preflight_script':'${project_root}/theme_watch_preflight.py','validate_script':'${project_root}/theme_watch_validate_reports.py','webhook_script':'${project_root}/theme_watch_feishu_webhook.py','latest_run_id':'${latest_run_id}','latest_run_url':'${latest_run_url}','summary_dir':'${project_root}/logs/theme_watch_workflow','report_root':'${project_root}/reports/theme_watch','notification_mode':'feishu_webhook','base_sync_mode':'disabled'}; print(json.dumps(payload, ensure_ascii=False))"
    outputs:
      handoff_payload: json
    on_failure:
      action:
        tool: shell_command
        args:
          command: Write-Output '{"result":"handoff_payload_failed"}'
      outputs:
        handoff_payload: json
      result: handoff_failed

handoff_contract:
  version: 1
  producer_agent: ${current_agent_name}
  consumer_agent: ${next_agent_name}
  transport: json
  required_fields:
    - name: workflow_file
      type: string
      format: path
    - name: preflight_script
      type: string
      format: path
    - name: validate_script
      type: string
      format: path
    - name: webhook_script
      type: string
      format: path
    - name: latest_run_id
      type: string
      format: github_actions_run_id
    - name: latest_run_url
      type: string
      format: uri
    - name: summary_dir
      type: string
      format: path
    - name: report_root
      type: string
      format: path
    - name: notification_mode
      type: string
      enum:
        - feishu_webhook
    - name: base_sync_mode
      type: string
      enum:
        - disabled
    - name: latest_run_status
      type: object
      schema:
        conclusion: string
        jobs:
          update: string
          deploy: string
          notify: string
          verify_pages: string
  optional_fields:
    - name: normalized_phase_facts
      type: object
    - name: required_files_check
      type: object
    - name: validation_logic_facts
      type: object
    - name: archive_file
      type: string
      format: path
  rejection_conditions:
    - ${latest_run_status.conclusion} != "success"
    - ${required_files_check.missing_count} > 0
    - ${notification_mode} != "feishu_webhook"
  acceptance_conditions:
    - ${latest_run_status.conclusion} == "success"
    - ${latest_run_status.jobs.update} == "success"
    - ${latest_run_status.jobs.deploy} == "success"
    - ${latest_run_status.jobs.notify} == "success"
    - ${latest_run_status.jobs.verify_pages} == "success"
  downstream_entrypoints:
    - agent_name: ${next_agent_name}
      start_step_id: emit_handoff_payload
      input_payload: ${handoff_payload}
```

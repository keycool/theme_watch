from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from theme_watch_config import CORRELATION_DIR, PAGE_DIR, THEME_DAILIES, TOPIC_PAGES


ROOT = Path(__file__).resolve().parent
DEFAULT_SCAN_CSV = ROOT / "sw_l2_strategy_scan.csv"
DEFAULT_MASTER_HISTORY = ROOT / ".cache_scan_v2" / "sw_daily_full_history.csv"
DEFAULT_WORKFLOW_NAME = "theme-watch-daily-update"
DEFAULT_RUNS_TABLE = "workflow_runs"
DEFAULT_SCAN_TABLE = "industry_scan_daily"
DEFAULT_LARK_CLI_CANDIDATES = ("lark-cli.cmd", "lark-cli", "lark-cli.ps1")


@dataclass
class SyncContext:
    base_token: str
    identity: str
    runs_table: str
    scan_table: str
    dry_run: bool
    lark_cli_bin: str
    table_fields_cache: dict[str, set[str]]
    skipped_fields_logged: set[tuple[str, tuple[str, ...]]]


def _resolve_lark_cli_bin(explicit: str | None = None) -> str:
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)
    env_bin = os.getenv("LARK_CLI_BIN", "")
    if env_bin:
        candidates.append(env_bin)
    candidates.extend(DEFAULT_LARK_CLI_CANDIDATES)

    for candidate in candidates:
        resolved = shutil.which(candidate) if not Path(candidate).exists() else candidate
        if resolved:
            return resolved
    raise RuntimeError(
        "Unable to find lark-cli executable. Set --lark-cli-bin or LARK_CLI_BIN explicitly."
    )


def _run_cli(args: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "lark-cli command failed:\n"
            f"command={' '.join(args)}\n"
            f"stdout={completed.stdout}\n"
            f"stderr={completed.stderr}"
        )

    stdout = completed.stdout.strip()
    if not stdout:
        return {}
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse lark-cli JSON output: {stdout}") from exc


def _record_list(
    ctx: SyncContext,
    table: str,
    field_ids: list[str],
    filter_json: dict[str, Any],
) -> list[dict[str, Any]]:
    args = [
        ctx.lark_cli_bin,
        "base",
        "+record-list",
        "--as",
        ctx.identity,
        "--base-token",
        ctx.base_token,
        "--table-id",
        table,
        "--format",
        "json",
        "--limit",
        "20",
        "--filter-json",
        json.dumps(filter_json, ensure_ascii=False),
    ]
    for field_id in field_ids:
        args.extend(["--field-id", field_id])

    payload = _run_cli(args)
    return _extract_record_items(payload)


def _record_search(
    ctx: SyncContext,
    table: str,
    keyword: str,
    search_field: str,
    field_ids: list[str],
    limit: int = 20,
) -> list[dict[str, Any]]:
    args = [
        ctx.lark_cli_bin,
        "base",
        "+record-search",
        "--as",
        ctx.identity,
        "--base-token",
        ctx.base_token,
        "--table-id",
        table,
        "--format",
        "json",
        "--keyword",
        keyword,
        "--search-field",
        search_field,
        "--limit",
        str(limit),
    ]
    for field_id in field_ids:
        args.extend(["--field-id", field_id])

    payload = _run_cli(args)
    if not isinstance(payload, dict):
        return []

    data = payload.get("data", {})
    rows = data.get("data", [])
    record_ids = data.get("record_id_list", [])
    fields = data.get("fields", [])
    if not isinstance(rows, list) or not isinstance(record_ids, list) or not isinstance(fields, list):
        return []

    items: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, list):
            continue
        field_map = {str(fields[i]): row[i] for i in range(min(len(fields), len(row)))}
        record_id = record_ids[idx] if idx < len(record_ids) else None
        items.append({"record_id": record_id, "fields": field_map})
    return items


def _field_list(ctx: SyncContext, table: str) -> set[str]:
    cached = ctx.table_fields_cache.get(table)
    if cached is not None:
        return cached

    args = [
        ctx.lark_cli_bin,
        "base",
        "+field-list",
        "--as",
        ctx.identity,
        "--base-token",
        ctx.base_token,
        "--table-id",
        table,
        "--format",
        "json",
    ]
    payload = _run_cli(args)
    fields = payload.get("data", {}).get("fields", []) if isinstance(payload, dict) else []
    names = {
        str(item.get("name"))
        for item in fields
        if isinstance(item, dict) and item.get("name")
    }
    ctx.table_fields_cache[table] = names
    return names


def _filter_existing_fields(ctx: SyncContext, table: str, field_map: dict[str, Any]) -> dict[str, Any]:
    if ctx.dry_run:
        return field_map

    allowed = _field_list(ctx, table)
    filtered = {key: value for key, value in field_map.items() if key in allowed}
    missing = sorted(set(field_map) - set(filtered))
    if missing:
        cache_key = (table, tuple(missing))
        if cache_key not in ctx.skipped_fields_logged:
            ctx.skipped_fields_logged.add(cache_key)
            print(
                json.dumps(
                    {
                        "table": table,
                        "skipped_missing_fields": missing,
                    },
                    ensure_ascii=False,
                )
            )
    return filtered


def _extract_record_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        return []

    candidates = [
        payload.get("items"),
        payload.get("data", {}).get("items") if isinstance(payload.get("data"), dict) else None,
        payload.get("data", {}).get("records") if isinstance(payload.get("data"), dict) else None,
        payload.get("records"),
    ]
    for candidate in candidates:
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
    return []


def _extract_record_id(record: dict[str, Any]) -> str | None:
    for key in ("record_id", "recordId", "id"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _extract_record_fields(record: dict[str, Any]) -> dict[str, Any]:
    fields = record.get("fields")
    if isinstance(fields, dict):
        return fields
    return {}


def _find_existing_record_id(
    ctx: SyncContext,
    table: str,
    key_field: str,
    key_value: str,
) -> str | None:
    records = _record_search(ctx, table, keyword=key_value, search_field=key_field, field_ids=[key_field], limit=50)
    for record in records:
        fields = _extract_record_fields(record)
        raw_value = fields.get(key_field, "")
        if isinstance(raw_value, list):
            normalized = raw_value[0] if raw_value else ""
        else:
            normalized = raw_value
        if str(normalized) == key_value:
            return _extract_record_id(record)
    return None


def _upsert_record(
    ctx: SyncContext,
    table: str,
    key_field: str,
    key_value: str,
    field_map: dict[str, Any],
) -> None:
    record_id = None if ctx.dry_run else _find_existing_record_id(ctx, table, key_field, key_value)
    filtered_field_map = _filter_existing_fields(ctx, table, field_map)
    args = [
        ctx.lark_cli_bin,
        "base",
        "+record-upsert",
        "--as",
        ctx.identity,
        "--base-token",
        ctx.base_token,
        "--table-id",
        table,
        "--format",
        "json",
        "--json",
        json.dumps(filtered_field_map, ensure_ascii=False),
    ]
    if record_id:
        args.extend(["--record-id", record_id])

    if ctx.dry_run:
        action = "update" if record_id else "create"
        print(
            json.dumps(
                {
                    "table": table,
                    "action": action,
                    "key_field": key_field,
                    "key_value": key_value,
                    "field_map": filtered_field_map,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    _run_cli(args)


def _count_official_pages() -> int:
    return sum(1 for page in TOPIC_PAGES if (PAGE_DIR / page["output"]).exists())


def _count_official_correlations() -> int:
    return sum(1 for item in THEME_DAILIES if (CORRELATION_DIR / item["output"]).exists())


def _infer_master_max_date(path: Path) -> str | None:
    if not path.exists():
        return None
    df = pd.read_csv(path, usecols=["trade_date"], dtype={"trade_date": str})
    if df.empty:
        return None
    return str(df["trade_date"].astype(str).max())


def _normalize_timestamp(value: str | None) -> str | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def _build_run_field_map(
    run_id: str,
    workflow_name: str,
    trigger_type: str,
    status: str,
    end_date: str,
    is_trade_day: bool,
    started_at: str | None,
    finished_at: str | None,
    scan_df: pd.DataFrame | None,
    issues_count: int,
    issues_summary: str,
    stdout_excerpt: str,
    sw_daily_master_max_date: str | None,
    artifact_url: str | None,
    pages_url: str | None,
) -> dict[str, Any]:
    latest_scan_date = None
    scan_rows = None
    if scan_df is not None and not scan_df.empty:
        latest_scan_date = str(scan_df["latest_date"].astype(str).max())
        scan_rows = int(len(scan_df))

    field_map: dict[str, Any] = {
        "run_id": run_id,
        "workflow_name": workflow_name,
        "trigger_type": trigger_type,
        "status": status,
        "end_date": end_date,
        "is_trade_day": is_trade_day,
        "correlation_file_count": _count_official_correlations(),
        "page_file_count": _count_official_pages(),
        "issues_count": issues_count,
    }
    if started_at:
        field_map["started_at"] = started_at
    if finished_at:
        field_map["finished_at"] = finished_at
    if sw_daily_master_max_date:
        field_map["sw_daily_master_max_date"] = sw_daily_master_max_date
    if latest_scan_date:
        field_map["scan_latest_date"] = latest_scan_date
    if scan_rows is not None:
        field_map["scan_rows"] = scan_rows
    if issues_summary:
        field_map["issues_summary"] = issues_summary
    if stdout_excerpt:
        field_map["stdout_excerpt"] = stdout_excerpt
    if artifact_url:
        field_map["artifact_url"] = artifact_url
    if pages_url:
        field_map["pages_url"] = pages_url
    return field_map


def _load_scan_df(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing scan CSV: {path}")
    return pd.read_csv(path)


def _bool_or_none(value: Any) -> bool | None:
    if pd.isna(value):
        return None
    return bool(value)


def _text_or_none(value: Any) -> str | None:
    if pd.isna(value):
        return None
    text = str(value)
    return text if text else None


def _number_or_none(value: Any) -> float | int | None:
    if pd.isna(value):
        return None
    return float(value)


def _sync_run_row(ctx: SyncContext, field_map: dict[str, Any]) -> None:
    _upsert_record(ctx, ctx.runs_table, "run_id", str(field_map["run_id"]), field_map)


def _build_scan_field_maps(run_id: str, scan_df: pd.DataFrame) -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    for _, row in scan_df.iterrows():
        snapshot_key = f"{run_id}::{row['industry_code']}"
        field_map: dict[str, Any] = {
            "snapshot_key": snapshot_key,
            "run_id": run_id,
            "trade_date": str(row["latest_date"]),
            "industry_code": str(row["industry_code"]),
            "industry_name": str(row["industry_name"]),
            "l1_name": str(row["l1_name"]),
        }

        optional_text = {
            "prefilter_label": row.get("prefilter_label"),
            "final_label": row.get("final_label"),
            "crowding_label": row.get("crowding_label"),
            "summary_line": row.get("summary_line"),
            "leader_top1_name": row.get("leader_top1_name"),
        }
        for key, value in optional_text.items():
            normalized = _text_or_none(value)
            if normalized is not None:
                field_map[key] = normalized

        optional_numbers = {
            "total_mv_yi": row.get("total_mv_yi"),
            "leader_top1_pct_change": row.get("leader_top1_pct_change"),
            "leader_count": row.get("leader_count"),
            "leader_active_count": row.get("leader_active_count"),
            "absorption_rate": row.get("absorption_rate"),
            "absorption_rate_rank_pct": row.get("absorption_rate_rank_pct"),
            "absorption_rate_5d_change": row.get("absorption_rate_5d_change"),
            "close_to_ma60_gap": row.get("close_to_ma60_gap"),
            "ma60_slope_20d": row.get("ma60_slope_20d"),
        }
        for key, value in optional_numbers.items():
            normalized = _number_or_none(value)
            if normalized is not None:
                field_map[key] = normalized

        optional_bools = {
            "breakout_emerged": row.get("breakout_emerged"),
            "breakout_confirmed": row.get("breakout_confirmed"),
            "local_activity_ok": row.get("local_activity_ok"),
            "has_ma250": row.get("has_ma250"),
            "has_amount_ma20": row.get("has_amount_ma20"),
            "has_ret_120d_rank": row.get("has_ret_120d_rank"),
        }
        for key, value in optional_bools.items():
            normalized = _bool_or_none(value)
            if normalized is not None:
                field_map[key] = normalized

        rows.append((snapshot_key, field_map))
    return rows


def _sync_scan_rows(ctx: SyncContext, run_id: str, scan_df: pd.DataFrame) -> None:
    for snapshot_key, field_map in _build_scan_field_maps(run_id, scan_df):
        _upsert_record(ctx, ctx.scan_table, "snapshot_key", snapshot_key, field_map)


def _read_excerpt(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[-20:])


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync theme watch run data to Feishu Base.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--base-token", default=os.getenv("THEME_WATCH_BASE_TOKEN", ""))
    parser.add_argument("--identity", default=os.getenv("THEME_WATCH_BASE_IDENTITY", "user"))
    parser.add_argument("--runs-table", default=os.getenv("THEME_WATCH_RUNS_TABLE", DEFAULT_RUNS_TABLE))
    parser.add_argument("--scan-table", default=os.getenv("THEME_WATCH_SCAN_TABLE", DEFAULT_SCAN_TABLE))
    parser.add_argument("--lark-cli-bin", default=os.getenv("LARK_CLI_BIN", ""))
    parser.add_argument("--workflow-name", default=DEFAULT_WORKFLOW_NAME)
    parser.add_argument("--trigger-type", default="manual")
    parser.add_argument("--status", default="success")
    parser.add_argument("--end-date", default=datetime.now().strftime("%Y%m%d"))
    parser.add_argument("--started-at")
    parser.add_argument("--finished-at")
    parser.add_argument("--issues-count", type=int)
    parser.add_argument("--issues-summary", default="")
    parser.add_argument("--stdout-file")
    parser.add_argument("--stdout-excerpt", default="")
    parser.add_argument("--artifact-url")
    parser.add_argument("--pages-url")
    parser.add_argument("--scan-csv", default=str(DEFAULT_SCAN_CSV))
    parser.add_argument("--master-history", default=str(DEFAULT_MASTER_HISTORY))
    parser.add_argument("--sw-daily-master-max-date")
    parser.add_argument("--is-trade-day", action="store_true")
    parser.add_argument("--skip-run", action="store_true")
    parser.add_argument("--skip-scan", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if not args.base_token and not args.dry_run:
        raise RuntimeError("Missing base token. Provide --base-token or THEME_WATCH_BASE_TOKEN.")

    ctx = SyncContext(
        base_token=args.base_token or "dry-run-base-token",
        identity=args.identity,
        runs_table=args.runs_table,
        scan_table=args.scan_table,
        dry_run=args.dry_run,
        lark_cli_bin=_resolve_lark_cli_bin(args.lark_cli_bin),
        table_fields_cache={},
        skipped_fields_logged=set(),
    )

    scan_df = None if args.skip_scan else _load_scan_df(Path(args.scan_csv))
    issues_count = args.issues_count
    if issues_count is None:
        issues_count = 1 if args.issues_summary else 0

    stdout_excerpt = args.stdout_excerpt or _read_excerpt(Path(args.stdout_file)) if args.stdout_file else args.stdout_excerpt
    sw_daily_master_max_date = args.sw_daily_master_max_date or _infer_master_max_date(Path(args.master_history))
    started_at = _normalize_timestamp(args.started_at) if args.started_at else None
    finished_at = _normalize_timestamp(args.finished_at) if args.finished_at else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not args.skip_run:
        run_field_map = _build_run_field_map(
            run_id=args.run_id,
            workflow_name=args.workflow_name,
            trigger_type=args.trigger_type,
            status=args.status,
            end_date=args.end_date,
            is_trade_day=args.is_trade_day,
            started_at=started_at,
            finished_at=finished_at,
            scan_df=scan_df,
            issues_count=issues_count,
            issues_summary=args.issues_summary,
            stdout_excerpt=stdout_excerpt,
            sw_daily_master_max_date=sw_daily_master_max_date,
            artifact_url=args.artifact_url,
            pages_url=args.pages_url,
        )
        _sync_run_row(ctx, run_field_map)

    if scan_df is not None:
        _sync_scan_rows(ctx, args.run_id, scan_df)


if __name__ == "__main__":
    main()

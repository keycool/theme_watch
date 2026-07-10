from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from theme_watch_config import CORRELATION_DIR, PAGE_DIR, THEME_DAILIES, TOPIC_PAGES
from theme_watch_dashboard import _live_cards


ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
SUMMARY_DIR = LOG_DIR / "theme_watch_workflow"
UPDATE_SCRIPT = ROOT / "daily_update_theme_watch.py"
SCAN_CSV = ROOT / "sw_l2_strategy_scan.csv"
INDEX_HTML = ROOT / "reports" / "theme_watch" / "index.html"


@dataclass
class RunResult:
    run_id: str
    end_date: str
    started_at: datetime
    finished_at: datetime
    returncode: int
    stdout_path: Path
    summary_path: Path
    status: str
    issues: list[str]
    is_trade_day: bool
    metrics: dict[str, Any]


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _default_end_date() -> str:
    if os.getenv("GITHUB_ACTIONS") == "true":
        return (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    now = datetime.now()
    if now.hour < 20:
        return (now - timedelta(days=1)).strftime("%Y%m%d")
    return now.strftime("%Y%m%d")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run theme watch update with self-check.")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--trigger-type", default="manual")
    parser.add_argument("--allow-non-trade-day", action="store_true")
    parser.add_argument("--skip-sync", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _parse_key_value_output(text: str) -> dict[str, str]:
    metrics: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        metrics[key.strip()] = value.strip()
    return metrics


def _expected_correlation_paths() -> list[Path]:
    return [CORRELATION_DIR / item["output"] for item in THEME_DAILIES]


def _expected_page_paths() -> list[Path]:
    return [PAGE_DIR / page["output"] for page in TOPIC_PAGES]


def _recent_file_count(paths: list[Path], started_at: datetime) -> int:
    threshold = started_at.timestamp() - 2
    count = 0
    for path in paths:
        if path.exists() and path.stat().st_mtime >= threshold:
            count += 1
    return count


def _load_scan_latest_date() -> tuple[str | None, int]:
    if not SCAN_CSV.exists():
        return None, 0
    df = pd.read_csv(SCAN_CSV)
    if df.empty or "latest_date" not in df.columns:
        return None, len(df)
    latest_date = str(df["latest_date"].astype(str).max())
    return latest_date, len(df)


def _day_gap(expected_date: str, actual_date: str) -> int | None:
    try:
        expected = datetime.strptime(expected_date, "%Y%m%d").date()
        actual = datetime.strptime(actual_date, "%Y%m%d").date()
    except ValueError:
        return None
    return (expected - actual).days


def _infer_is_trade_day(metrics: dict[str, str], returncode: int) -> bool:
    if "skip_non_trade_day" in metrics:
        return False
    if returncode != 0:
        return False
    return True


def _check_index_links() -> list[str]:
    if not INDEX_HTML.exists():
        return ["首页缺失: reports/theme_watch/index.html 未生成。"]

    html = INDEX_HTML.read_text(encoding="utf-8")
    issues: list[str] = []
    expected_hrefs = sorted({str(card["href"]) for card in _live_cards() if card.get("href")})
    for href in expected_hrefs:
        if href not in html:
            issues.append(f"首页缺少专题链接: {href}")
    return issues


def _build_issues(
    end_date: str,
    started_at: datetime,
    returncode: int,
    metrics: dict[str, str],
) -> tuple[str, list[str], bool]:
    issues: list[str] = []
    is_trade_day = _infer_is_trade_day(metrics, returncode)

    if returncode != 0:
        issues.append("daily_update_theme_watch.py 执行失败，请先查看 stdout 日志。")
        return "failed", issues, is_trade_day

    if "skip_non_trade_day" in metrics:
        return "skipped", issues, False

    sw_daily_master_max_date = metrics.get("sw_daily_master_max_date")
    if not sw_daily_master_max_date:
        issues.append("缺少 sw_daily_master_max_date 输出，无法确认 Tushare 主缓存是否更新。")
    elif sw_daily_master_max_date != end_date:
        master_gap = _day_gap(end_date, sw_daily_master_max_date)
        if master_gap is not None and master_gap <= 1:
            metrics["sw_daily_master_lag_days"] = str(master_gap)
        else:
            issues.append(
                f"Tushare 主缓存最新日期异常: 期望 {end_date}，实际 {sw_daily_master_max_date}。"
            )

    scan_latest_date = metrics.get("scan_latest_date")
    scan_rows = metrics.get("scan_rows")
    loaded_scan_latest_date, loaded_scan_rows = _load_scan_latest_date()
    if not scan_latest_date and loaded_scan_latest_date:
        scan_latest_date = loaded_scan_latest_date
    if not scan_rows and loaded_scan_rows:
        scan_rows = str(loaded_scan_rows)

    if not scan_latest_date:
        issues.append("缺少 scan_latest_date，申万二级扫描结果未确认。")
    elif scan_latest_date != end_date:
        scan_gap = _day_gap(end_date, scan_latest_date)
        if scan_gap is not None and scan_gap <= 1:
            metrics["scan_latest_lag_days"] = str(scan_gap)
        else:
            issues.append(f"申万二级扫描最新日期异常: 期望 {end_date}，实际 {scan_latest_date}。")

    if not scan_rows or int(float(scan_rows)) <= 0:
        issues.append("申万二级扫描结果为空。")

    correlation_paths = _expected_correlation_paths()
    recent_correlation_count = _recent_file_count(correlation_paths, started_at)
    missing_correlation = [path.name for path in correlation_paths if not path.exists()]
    if missing_correlation:
        issues.append(f"相关性 CSV 缺失 {len(missing_correlation)} 个: {', '.join(missing_correlation[:5])}")
    elif recent_correlation_count != len(correlation_paths):
        issues.append(
            f"相关性 CSV 未全部重算: 期望 {len(correlation_paths)} 个，最近更新 {recent_correlation_count} 个。"
        )

    page_paths = _expected_page_paths()
    recent_page_count = _recent_file_count(page_paths, started_at)
    missing_pages = [path.name for path in page_paths if not path.exists()]
    if missing_pages:
        issues.append(f"专题页缺失 {len(missing_pages)} 个: {', '.join(missing_pages[:5])}")
    elif recent_page_count != len(page_paths):
        issues.append(
            f"专题页未全部重建: 期望 {len(page_paths)} 个，最近更新 {recent_page_count} 个。"
        )

    if not INDEX_HTML.exists():
        issues.append("首页缺失: reports/theme_watch/index.html 未生成。")
    elif INDEX_HTML.stat().st_mtime < started_at.timestamp() - 2:
        issues.append("首页未在本次运行中重建。")
    else:
        issues.extend(_check_index_links())

    status = "success" if not issues else "warning"
    return status, issues, is_trade_day


def _write_summary(result: RunResult) -> None:
    payload = {
        "run_id": result.run_id,
        "end_date": result.end_date,
        "started_at": result.started_at.isoformat(),
        "finished_at": result.finished_at.isoformat(),
        "returncode": result.returncode,
        "status": result.status,
        "is_trade_day": result.is_trade_day,
        "issues": result.issues,
        "metrics": result.metrics,
        "stdout_path": str(result.stdout_path),
    }
    result.summary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _run_update(args: argparse.Namespace, stdout_path: Path) -> tuple[int, str]:
    command = [sys.executable, str(UPDATE_SCRIPT), "--end-date", args.end_date]
    if args.allow_non_trade_day:
        command.append("--allow-non-trade-day")
    if args.dry_run:
        command.append("--dry-run")

    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    combined = completed.stdout
    if completed.stderr:
        combined = combined + ("\n" if combined else "") + completed.stderr
    stdout_path.write_text(combined, encoding="utf-8")
    return completed.returncode, combined


def _tail_lines(text: str, max_lines: int = 120) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[-max_lines:])


def main() -> None:
    args = _build_parser().parse_args()
    args.end_date = args.end_date or _default_end_date()
    run_id = args.run_id or f"{args.trigger_type}-{_now_stamp()}"
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now()
    stdout_path = SUMMARY_DIR / f"{run_id}.log"
    summary_path = SUMMARY_DIR / f"{run_id}.json"

    returncode, output = _run_update(args, stdout_path)
    metrics = _parse_key_value_output(output)
    finished_at = datetime.now()
    status, issues, is_trade_day = _build_issues(args.end_date, started_at, returncode, metrics)

    result = RunResult(
        run_id=run_id,
        end_date=args.end_date,
        started_at=started_at,
        finished_at=finished_at,
        returncode=returncode,
        stdout_path=stdout_path,
        summary_path=summary_path,
        status=status,
        issues=issues,
        is_trade_day=is_trade_day,
        metrics=metrics,
    )

    print(f"run_id={result.run_id}")
    if result.returncode != 0 and result.stdout_path.exists():
        print("daily_update_tail_start")
        print(_tail_lines(result.stdout_path.read_text(encoding="utf-8"), max_lines=120))
        print("daily_update_tail_end")

    _write_summary(result)
    print(f"status={result.status}")
    print(f"issues_count={len(result.issues)}")
    print(f"summary_json={result.summary_path}")
    print(f"stdout_log={result.stdout_path}")
    for issue in result.issues:
        print(f"issue={issue}")

    if result.status == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
DEFAULT_SUMMARY_DIR = ROOT / "logs" / "theme_watch_workflow"
DEFAULT_SCAN_CSV = ROOT / "sw_l2_strategy_scan.csv"


def _latest_summary_path(summary_dir: Path) -> Path:
    candidates = sorted(summary_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No workflow summary JSON found in {summary_dir}")
    return candidates[0]


def _summary_sheet(payload: dict) -> pd.DataFrame:
    rows = [
        ("run_id", payload.get("run_id", "")),
        ("end_date", payload.get("end_date", "")),
        ("status", payload.get("status", "")),
        ("returncode", payload.get("returncode", "")),
        ("is_trade_day", payload.get("is_trade_day", "")),
        ("started_at", payload.get("started_at", "")),
        ("finished_at", payload.get("finished_at", "")),
        ("stdout_path", payload.get("stdout_path", "")),
    ]
    return pd.DataFrame(rows, columns=["field", "value"])


def _issues_sheet(payload: dict) -> pd.DataFrame:
    issues = payload.get("issues", [])
    return pd.DataFrame({"issue": issues if issues else [""]})


def _metrics_sheet(payload: dict) -> pd.DataFrame:
    metrics = payload.get("metrics", {})
    return pd.DataFrame([(key, value) for key, value in metrics.items()], columns=["metric", "value"])


def build_workbook(summary_dir: Path, scan_csv: Path, output_xlsx: Path) -> Path:
    summary_path = _latest_summary_path(summary_dir)
    payload = json.loads(summary_path.read_text(encoding="utf-8"))

    output_xlsx.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_xlsx, engine="openpyxl") as writer:
        _summary_sheet(payload).to_excel(writer, index=False, sheet_name="workflow_summary")
        _issues_sheet(payload).to_excel(writer, index=False, sheet_name="issues")
        _metrics_sheet(payload).to_excel(writer, index=False, sheet_name="metrics")
        if scan_csv.exists():
            pd.read_csv(scan_csv).to_excel(writer, index=False, sheet_name="scan_snapshot")

    print(f"artifact_xlsx={output_xlsx}")
    print(f"artifact_summary_json={summary_path}")
    return output_xlsx


def main() -> None:
    parser = argparse.ArgumentParser(description="Build local workbook artifacts for theme watch workflow.")
    parser.add_argument("--summary-dir", default=str(DEFAULT_SUMMARY_DIR))
    parser.add_argument("--scan-csv", default=str(DEFAULT_SCAN_CSV))
    parser.add_argument("--output-xlsx", required=True)
    args = parser.parse_args()

    build_workbook(
        summary_dir=Path(args.summary_dir),
        scan_csv=Path(args.scan_csv),
        output_xlsx=Path(args.output_xlsx),
    )


if __name__ == "__main__":
    main()

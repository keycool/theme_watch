import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

from industry_start_cached_scan_v2 import run_scan


LOG_PATH = Path(__file__).with_name("wait_and_seed_sw_cache.log")
SUMMARY_PATH = Path(__file__).with_name("industry_start_scan_summary.txt")


def log(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Retry the cached industry scan until SW daily data can be fetched and cached."
    )
    parser.add_argument(
        "--interval-minutes",
        type=int,
        default=60,
        help="Minutes to wait between retries after a rate-limit failure.",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=24,
        help="Maximum retry attempts before giving up.",
    )
    parser.add_argument(
        "--end-date",
        default="20260630",
        help="End date passed to the scan script in YYYYMMDD format.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="Number of top candidate industries to include in the success summary.",
    )
    return parser.parse_args()


def format_bool(value) -> str:
    if pd.isna(value):
        return "-"
    return "Y" if bool(value) else "N"


def build_summary(df: pd.DataFrame, top_n: int) -> str:
    if df.empty:
        return "No candidate industries were produced."

    top = df.head(top_n).copy()
    lines = []
    lines.append(f"Top {min(len(top), top_n)} candidate industries")
    lines.append(
        "industry | score | conv | breakout | leader | ret_120d | ret_rank_pct | leader_name | latest_date"
    )
    for _, row in top.iterrows():
        lines.append(
            " | ".join(
                [
                    str(row["industry_name"]),
                    str(int(row["score"])),
                    format_bool(row["convergence_ok"]),
                    format_bool(row["breakout_ok"]),
                    format_bool(row["leader_ok"]),
                    f"{float(row['ret_120d']):.2%}" if not pd.isna(row["ret_120d"]) else "-",
                    f"{float(row['ret_rank_pct']):.0%}" if not pd.isna(row["ret_rank_pct"]) else "-",
                    str(row["leader_name"]) if pd.notna(row["leader_name"]) else "-",
                    str(row["latest_date"]),
                ]
            )
        )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    interval_seconds = max(args.interval_minutes, 1) * 60

    log(
        f"Starting retry loop: interval={args.interval_minutes} minutes, max_attempts={args.max_attempts}, end_date={args.end_date}"
    )

    for attempt in range(1, args.max_attempts + 1):
        log(f"Attempt {attempt} started")
        try:
            df = run_scan(end_date=args.end_date)
            output_path = Path(__file__).with_name("industry_start_scan_result.csv")
            df.to_csv(output_path, index=False, encoding="utf-8-sig")
            summary = build_summary(df, args.top_n)
            SUMMARY_PATH.write_text(summary, encoding="utf-8")
            log(f"Attempt {attempt} succeeded, wrote {len(df)} rows to {output_path}")
            log(f"Summary written to {SUMMARY_PATH}")
            print(summary)
            return 0
        except RuntimeError as exc:
            message = str(exc)
            if "rate-limited" in message:
                log(f"Attempt {attempt} hit rate limit: {message}")
                if attempt == args.max_attempts:
                    break
                log(f"Sleeping for {args.interval_minutes} minutes before retry")
                time.sleep(interval_seconds)
                continue
            log(f"Attempt {attempt} failed with non-rate-limit runtime error: {message}")
            return 1
        except Exception as exc:
            log(f"Attempt {attempt} failed with unexpected error: {exc}")
            return 1

    log("Retry loop ended without success")
    return 2


if __name__ == "__main__":
    sys.exit(main())

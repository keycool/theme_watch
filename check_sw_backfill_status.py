from pathlib import Path
import sys

import pandas as pd


BASE_DIR = Path(__file__).parent
LOG_PATH = BASE_DIR / "sw_backfill_scheduler.log"
MASTER_PATH = BASE_DIR / ".cache_scan_v2" / "sw_daily_full_history.csv"


def tail_lines(path: Path, max_lines: int = 12) -> str:
    if not path.exists():
        return "(missing)"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines:
        return "(empty)"
    return "\n".join(lines[-max_lines:])


def summarize_master(path: Path) -> str:
    if not path.exists():
        return "master_cache: missing"
    df = pd.read_csv(path, dtype={"ts_code": str, "trade_date": str})
    if df.empty:
        return "master_cache: empty"
    return (
        f"master_cache: rows={len(df)}, "
        f"codes={df['ts_code'].nunique()}, "
        f"dates={df['trade_date'].nunique()}, "
        f"min_date={df['trade_date'].min()}, "
        f"max_date={df['trade_date'].max()}"
    )


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("SW Daily Backfill Status")
    print(summarize_master(MASTER_PATH))
    print()
    print("Last scheduler log lines:")
    print(tail_lines(LOG_PATH))


if __name__ == "__main__":
    main()

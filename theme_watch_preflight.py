from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
UPDATE_SCRIPT = ROOT / "daily_update_theme_watch.py"
VALIDATE_SCRIPT = ROOT / "theme_watch_validate_reports.py"


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild theme watch pages from cached data and validate output.")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--allow-non-trade-day", action="store_true")
    args = parser.parse_args()

    update_cmd = [
        sys.executable,
        str(UPDATE_SCRIPT),
        "--skip-fetch",
        "--skip-scan",
        "--allow-non-trade-day",
    ]
    if args.end_date:
        update_cmd.extend(["--end-date", args.end_date])
    if args.allow_non_trade_day:
        update_cmd.append("--allow-non-trade-day")

    completed = subprocess.run(update_cmd, cwd=ROOT, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)

    validate = subprocess.run([sys.executable, str(VALIDATE_SCRIPT)], cwd=ROOT, check=False)
    if validate.returncode != 0:
        raise SystemExit(validate.returncode)

    print("theme_watch_preflight_ok=1")


if __name__ == "__main__":
    main()

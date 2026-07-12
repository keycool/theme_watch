from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _run(args: list[str]) -> None:
    print(f"preflight_run={' '.join(args)}")
    subprocess.run(args, cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a local preflight for theme_watch generation and validation.")
    parser.add_argument("--end-date", default="", help="Optional YYYYMMDD passed to daily_update_theme_watch.py")
    parser.add_argument("--skip-rebuild", action="store_true", help="Only run structural validation.")
    args = parser.parse_args()

    if not args.skip_rebuild:
        cmd = [sys.executable, "daily_update_theme_watch.py", "--skip-fetch", "--skip-scan", "--skip-correlations", "--allow-non-trade-day"]
        if args.end_date:
            cmd.extend(["--end-date", args.end_date])
        _run(cmd)

    _run([sys.executable, "theme_watch_validate_reports.py"])
    print("theme_watch_preflight_ok=1")


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.request import Request, urlopen


LIVE_OVERVIEW_URL = (
    "https://raw.githubusercontent.com/keycool/theme_watch/"
    "etf-watch-data/overview.json"
)
DATE_PATTERN = re.compile(r"^\d{8}$")


def extract_latest_date(overview: dict) -> str:
    dates = {
        str(target.get("latestDate", ""))
        for target in overview.get("targets", [])
    }
    if len(dates) != 1:
        raise ValueError(
            f"Overview must contain one latestDate, found {sorted(dates)}."
        )
    latest_date = next(iter(dates))
    if not DATE_PATTERN.fullmatch(latest_date):
        raise ValueError(f"Invalid overview latestDate: {latest_date!r}.")
    return latest_date


def validate_publication_date(
    *,
    candidate_date: str,
    live_date: str,
    allow_rollback: bool,
    confirmation: str,
) -> None:
    if not DATE_PATTERN.fullmatch(candidate_date):
        raise ValueError(f"Invalid candidate date: {candidate_date!r}.")
    if not DATE_PATTERN.fullmatch(live_date):
        raise ValueError(f"Invalid live date: {live_date!r}.")
    if candidate_date >= live_date:
        return
    if not allow_rollback:
        raise ValueError(
            f"Publication date {candidate_date} is older than live date "
            f"{live_date}; rollback is blocked."
        )
    expected = f"ROLLBACK {candidate_date}"
    if confirmation != expected:
        raise ValueError(
            "Rollback confirmation does not match the required phrase "
            f"{expected!r}."
        )


def read_live_overview(url: str) -> dict:
    request = Request(
        url,
        headers={
            "User-Agent": "ETF-Watch-Workflow",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    candidate = parser.add_mutually_exclusive_group(required=True)
    candidate.add_argument("--candidate-date")
    candidate.add_argument("--candidate-overview", type=Path)
    parser.add_argument("--live-url", default=LIVE_OVERVIEW_URL)
    parser.add_argument("--allow-rollback", action="store_true")
    parser.add_argument("--confirmation", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.candidate_overview:
        candidate_overview = json.loads(
            args.candidate_overview.read_text(encoding="utf-8")
        )
        candidate_date = extract_latest_date(candidate_overview)
    else:
        candidate_date = args.candidate_date

    live_date = extract_latest_date(read_live_overview(args.live_url))
    try:
        validate_publication_date(
            candidate_date=candidate_date,
            live_date=live_date,
            allow_rollback=args.allow_rollback,
            confirmation=args.confirmation,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"candidate_date={candidate_date}")
    print(f"live_date={live_date}")
    print(f"rollback={str(candidate_date < live_date).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

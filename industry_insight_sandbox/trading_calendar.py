from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable, Mapping
from zoneinfo import ZoneInfo


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
MARKET_CLOSE_HOUR = 16


def completed_calendar_end(now: datetime | None = None) -> str:
    """Return the latest calendar date whose market session could be complete."""
    current = now or datetime.now(SHANGHAI_TZ)
    if current.tzinfo is None:
        current = current.replace(tzinfo=SHANGHAI_TZ)
    else:
        current = current.astimezone(SHANGHAI_TZ)
    cutoff = current.date()
    if current.hour < MARKET_CLOSE_HOUR:
        cutoff -= timedelta(days=1)
    return cutoff.strftime("%Y%m%d")


def calendar_start_date(end_date: str, live_latest_date: str | None = None) -> str:
    """Return a calendar query start that includes the live-to-current range."""
    end = datetime.strptime(end_date, "%Y%m%d").date()
    if live_latest_date:
        try:
            live = datetime.strptime(live_latest_date, "%Y%m%d").date()
        except ValueError:
            live = end - timedelta(days=30)
        start = min(live, end - timedelta(days=30))
    else:
        start = end - timedelta(days=30)
    return start.strftime("%Y%m%d")


def _open_trade_dates(
    calendar_rows: Iterable[Mapping[str, object]],
    cutoff_date: str,
) -> list[str]:
    return sorted(
        {
            str(row["cal_date"])
            for row in calendar_rows
            if str(row.get("is_open")) == "1"
            and str(row.get("cal_date")) <= cutoff_date
        }
    )


def latest_completed_trade_date(
    calendar_rows: Iterable[Mapping[str, object]],
    now: datetime | None = None,
) -> str:
    cutoff = completed_calendar_end(now)
    dates = _open_trade_dates(calendar_rows, cutoff)
    if not dates:
        raise ValueError(f"No completed SSE trade date found through {cutoff}.")
    return dates[-1]


def latest_unpublished_trade_date(
    calendar_rows: Iterable[Mapping[str, object]],
    live_latest_date: str | None,
    now: datetime | None = None,
) -> str:
    cutoff = completed_calendar_end(now)
    dates = _open_trade_dates(calendar_rows, cutoff)
    if not dates:
        raise ValueError(f"No completed SSE trade date found through {cutoff}.")

    if live_latest_date:
        unpublished = [
            trade_date for trade_date in dates if trade_date > live_latest_date
        ]
        if unpublished:
            return unpublished[-1]
    return dates[-1]

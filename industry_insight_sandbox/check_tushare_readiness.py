from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from guard_production_date import extract_latest_date
from trading_calendar import (
    calendar_start_date,
    completed_calendar_end,
    latest_unpublished_trade_date,
)


DEFAULT_TARGETS_PATH = Path(__file__).resolve().parent / "targets.json"
DEFAULT_HK_TARGETS_PATH = Path(__file__).resolve().parent / "hk_qdii_targets.json"
LIVE_OVERVIEW_URL = (
    "https://raw.githubusercontent.com/keycool/theme_watch/"
    "etf-watch-data/overview.json"
)


def clean_code(value) -> str | None:
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return None
    return text


def build_readiness_universe(
    targets: list[dict],
    etf_metadata_rows: list[dict],
) -> dict[str, list[str]]:
    etf_targets = sorted(
        {
            str(target["code"])
            for target in targets
            if target.get("kind") == "etf"
        }
    )
    direct_indexes = {
        str(target["code"])
        for target in targets
        if target.get("kind") == "index"
    }
    unsupported = sorted(
        {
            str(target.get("kind"))
            for target in targets
            if target.get("kind") not in {"etf", "index"}
        }
    )
    if unsupported:
        raise ValueError(f"Unsupported target kinds: {', '.join(unsupported)}")

    metadata_by_code = {
        str(row.get("ts_code")): clean_code(row.get("index_code"))
        for row in etf_metadata_rows
    }
    unresolved_etfs = sorted(
        code for code in etf_targets if not metadata_by_code.get(code)
    )
    tracking_indexes = sorted(
        direct_indexes
        | {
            metadata_by_code[code]
            for code in etf_targets
            if metadata_by_code.get(code)
        }
    )
    return {
        "etf_targets": etf_targets,
        "tracking_indexes": tracking_indexes,
        "unresolved_etfs": unresolved_etfs,
    }


def extend_with_hk_qdii(
    universe: dict[str, list[str]],
    hk_targets: list[dict],
) -> dict[str, list[str]]:
    unsupported = sorted(
        {
            str(target.get("kind"))
            for target in hk_targets
            if target.get("kind") != "hk_qdii"
        }
    )
    if unsupported:
        raise ValueError(f"Unsupported HK target kinds: {', '.join(unsupported)}")
    return {
        "etf_targets": sorted(
            set(universe["etf_targets"])
            | {str(target["code"]) for target in hk_targets}
        ),
        "tracking_indexes": sorted(
            set(universe["tracking_indexes"])
            | {
                str(target["readinessIndexCode"])
                for target in hk_targets
                if target.get("readinessIndexCode")
            }
        ),
        "global_indexes": sorted(
            {
                str(target["benchmarkCode"])
                for target in hk_targets
                if target.get("benchmarkCode")
            }
        ),
        "unresolved_etfs": universe["unresolved_etfs"],
    }


def frame_has_trade_date(frame, target_date: str, minimum_rows: int = 1) -> bool:
    if frame is None or frame.empty or "trade_date" not in frame:
        return False
    dates = set(frame["trade_date"].astype(str))
    return len(frame) >= minimum_rows and target_date in dates


def read_live_overview(url: str) -> dict:
    request = Request(
        url,
        headers={
            "User-Agent": "ETF-Watch-Readiness",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def live_overview_is_current(overview: dict, target_date: str) -> bool:
    return extract_latest_date(overview) >= target_date


def fetch_with_retry(fetcher: Callable, attempts: int = 3):
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return fetcher()
        except Exception as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Tushare readiness query failed: {last_error}") from last_error


def emit(key: str, value) -> None:
    if isinstance(value, bool):
        rendered = str(value).lower()
    elif isinstance(value, list):
        rendered = ",".join(value)
    else:
        rendered = str(value)
    print(f"{key}={rendered}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--targets", type=Path, default=DEFAULT_TARGETS_PATH)
    parser.add_argument(
        "--hk-targets",
        type=Path,
        default=DEFAULT_HK_TARGETS_PATH,
    )
    parser.add_argument("--target-date", help="Trade date in YYYYMMDD.")
    parser.add_argument("--live-overview-url", default=LIVE_OVERVIEW_URL)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    targets = json.loads(args.targets.read_text(encoding="utf-8"))
    hk_targets = json.loads(args.hk_targets.read_text(encoding="utf-8"))
    emit("target_count", len(targets) + len(hk_targets))

    live_latest_date: str | None = None
    try:
        live_overview = read_live_overview(args.live_overview_url)
        live_latest_date = extract_latest_date(live_overview)
        emit("live_latest_date", live_latest_date)
    except Exception as exc:
        print(f"Live overview check unavailable: {exc}", file=sys.stderr)
        emit("live_latest_date", "unavailable")

    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        raise SystemExit("TUSHARE_TOKEN is not configured.")

    import tushare as ts

    pro = ts.pro_api(token)

    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    calendar_end = completed_calendar_end(now)
    if args.target_date:
        target_date = args.target_date
        calendar_start = target_date
    else:
        calendar_start = calendar_start_date(calendar_end, live_latest_date)
        calendar = fetch_with_retry(
            lambda: pro.trade_cal(
                exchange="SSE",
                start_date=calendar_start,
                end_date=calendar_end,
                fields="cal_date,is_open",
            )
        )
        target_date = latest_unpublished_trade_date(
            calendar.to_dict("records"),
            live_latest_date,
            now,
        )

    emit("end_date", target_date)
    already_current = bool(
        live_latest_date and live_overview_is_current(
            {"targets": [{"latestDate": live_latest_date}]},
            target_date,
        )
    )
    emit("already_current", already_current)
    if already_current:
        emit("data_ready", False)
        emit("reason", "already_current")
        return 0

    calendar = fetch_with_retry(
        lambda: pro.trade_cal(
            exchange="SSE",
            start_date=target_date,
            end_date=target_date,
            fields="cal_date,is_open",
        )
    )
    if calendar.empty:
        raise RuntimeError(f"Trading calendar returned no row for {target_date}.")
    if int(calendar.iloc[0]["is_open"]) != 1:
        emit("data_ready", False)
        emit("reason", "non_trading_day")
        return 0

    etf_metadata = fetch_with_retry(
        lambda: pro.etf_basic(
            list_status="L",
            fields="ts_code,index_code,index_name",
        )
    )
    universe = extend_with_hk_qdii(
        build_readiness_universe(
            targets,
            etf_metadata.to_dict("records"),
        ),
        hk_targets,
    )
    etf_targets = universe["etf_targets"]
    tracking_indexes = universe["tracking_indexes"]
    global_indexes = universe["global_indexes"]
    unresolved_etfs = universe["unresolved_etfs"]

    stock_daily = fetch_with_retry(
        lambda: pro.daily(
            trade_date=target_date,
            fields="ts_code,trade_date,close",
        )
    )
    stock_daily_ready = frame_has_trade_date(
        stock_daily,
        target_date,
        minimum_rows=1000,
    )

    missing_etf_targets: list[str] = []
    for code in etf_targets:
        frame = fetch_with_retry(
            lambda code=code: pro.fund_daily(
                ts_code=code,
                start_date=target_date,
                end_date=target_date,
                fields="ts_code,trade_date,close",
            )
        )
        if not frame_has_trade_date(frame, target_date):
            missing_etf_targets.append(code)
        time.sleep(0.35)

    missing_tracking_indexes: list[str] = []
    for code in tracking_indexes:
        frame = fetch_with_retry(
            lambda code=code: pro.index_daily(
                ts_code=code,
                start_date=target_date,
                end_date=target_date,
                fields="ts_code,trade_date,close",
            )
        )
        if not frame_has_trade_date(frame, target_date):
            missing_tracking_indexes.append(code)
        time.sleep(0.35)

    missing_global_indexes: list[str] = []
    for code in global_indexes:
        frame = fetch_with_retry(
            lambda code=code: pro.index_global(
                ts_code=code,
                start_date=target_date,
                end_date=target_date,
                fields="ts_code,trade_date,close",
            )
        )
        if not frame_has_trade_date(frame, target_date):
            missing_global_indexes.append(code)
        time.sleep(0.35)

    data_ready = bool(
        stock_daily_ready
        and not unresolved_etfs
        and not missing_etf_targets
        and not missing_tracking_indexes
        and not missing_global_indexes
    )
    emit("stock_daily_rows", len(stock_daily))
    emit("stock_daily_ready", stock_daily_ready)
    emit("etf_target_count", len(etf_targets))
    emit("tracking_index_count", len(tracking_indexes))
    emit("global_index_count", len(global_indexes))
    emit("unresolved_etfs", unresolved_etfs)
    emit("missing_etf_targets", missing_etf_targets)
    emit("missing_tracking_indexes", missing_tracking_indexes)
    emit("missing_global_indexes", missing_global_indexes)
    emit("data_ready", data_ready)
    emit("reason", "ready" if data_ready else "daily_data_incomplete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

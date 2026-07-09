from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

from backfill_daily_market_history import backfill_daily_market
from backfill_sw_daily_history import backfill_history, get_pro, get_trade_days
from build_sw_l2_topic_report import build_topic_report
from build_theme_to_sw_l2_correlation import build_correlation
from run_sw_l2_strategy_scan import (
    OUTPUT_CSV,
    OUTPUT_LEADERBOARD_MD,
    OUTPUT_SUMMARY_MD,
    run_scan,
    write_leaderboard,
    write_summary,
)
from sw_data_utils import DEFAULT_END_DATE
from build_sw_l2_sample_pool import DEFAULT_THRESHOLD_YI
from theme_watch_config import CORRELATION_DIR, PAGE_DIR, THEME_DAILIES, TOPIC_PAGES
from theme_watch_dashboard import OUTPUT_HTML, build_dashboard


ROOT = Path(__file__).resolve().parent


def _default_end_date() -> str:
    return datetime.now().strftime("%Y%m%d")


def _lookback_start(end_date: str, lookback_days: int) -> str:
    end = datetime.strptime(end_date, "%Y%m%d")
    return (end - timedelta(days=max(lookback_days, 1))).strftime("%Y%m%d")


def _is_trade_day(end_date: str) -> bool:
    pro = get_pro()
    trade_days = get_trade_days(pro, start_date=end_date, end_date=end_date)
    return end_date in trade_days


def _run_scan(end_date: str, min_total_mv_yi: float) -> None:
    df = run_scan(end_date=end_date, min_total_mv_yi=min_total_mv_yi)
    if df.empty:
        raise RuntimeError("No L2 industries were scanned.")
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    write_summary(df, min_total_mv_yi=min_total_mv_yi)
    write_leaderboard(df, min_total_mv_yi=min_total_mv_yi)
    latest_date = df["latest_date"].dropna().astype(str).max()
    print(f"scan_latest_date={latest_date}")
    print(f"scan_rows={len(df)}")


def _refresh_correlations(start_date: str, end_date: str, force_refresh: bool) -> None:
    CORRELATION_DIR.mkdir(parents=True, exist_ok=True)
    for item in THEME_DAILIES:
        output = CORRELATION_DIR / item["output"]
        result = build_correlation(
            ts_code=item["ts_code"],
            source=item["source"],
            start_date=start_date,
            end_date=end_date,
            output=output,
            force_refresh=force_refresh,
        )
        top = result.iloc[0] if not result.empty else None
        top_text = "-" if top is None else f"{top['sw_code']} {top['corr_daily_ret']:.4f}"
        print(f"correlation {item['ts_code']} rows={len(result)} top={top_text}")


def _rebuild_topic_pages() -> None:
    PAGE_DIR.mkdir(parents=True, exist_ok=True)
    for page in TOPIC_PAGES:
        output = PAGE_DIR / page["output"]
        build_topic_report(codes=page["codes"], title=page["title"], output_path=output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Update SW L2 theme watch reports after market close.")
    parser.add_argument("--end-date", default=_default_end_date(), help="YYYYMMDD, default: today")
    parser.add_argument("--lookback-days", type=int, default=14)
    parser.add_argument("--correlation-start-date", default="20240101")
    parser.add_argument("--correlation-end-date", default=DEFAULT_END_DATE)
    parser.add_argument("--min-total-mv-yi", type=float, default=DEFAULT_THRESHOLD_YI)
    parser.add_argument("--skip-fetch", action="store_true")
    parser.add_argument("--skip-scan", action="store_true")
    parser.add_argument("--skip-theme-daily-refresh", action="store_true")
    parser.add_argument("--skip-correlations", action="store_true")
    parser.add_argument("--skip-pages", action="store_true")
    parser.add_argument(
        "--allow-non-trade-day",
        action="store_true",
        help="Run anyway even if end-date is not an SSE open trading day.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    start_date = _lookback_start(args.end_date, args.lookback_days)
    print(f"update_window={start_date}-{args.end_date}")

    if args.dry_run:
        print("dry_run=1")
        print(f"sw_daily_backfill={not args.skip_fetch}")
        print(f"strategy_scan={not args.skip_scan}")
        print(f"correlations={not args.skip_correlations}, force_theme_refresh={not args.skip_theme_daily_refresh}")
        print(f"topic_pages={not args.skip_pages}")
        print(f"dashboard={not args.skip_pages}")
        print(f"trade_day_guard={not args.allow_non_trade_day}")
        return

    if not args.allow_non_trade_day and not _is_trade_day(args.end_date):
        print(f"skip_non_trade_day={args.end_date}")
        return

    if not args.skip_fetch:
        sw = backfill_history(
            start_date=start_date,
            end_date=args.end_date,
            chunk_open_days=20,
            max_chunks=None,
            max_new_fetches=1,
            sleep_seconds=0,
        )
        print(f"sw_daily_master_max_date={sw['trade_date'].astype(str).max()}")

        fetched_market = backfill_daily_market(
            start_date=start_date,
            end_date=args.end_date,
            max_new_fetches=None,
            sleep_seconds=0,
        )
        print(f"new_daily_market_fetches={fetched_market}")

    if not args.skip_scan:
        _run_scan(end_date=args.end_date, min_total_mv_yi=args.min_total_mv_yi)

    if not args.skip_correlations:
        _refresh_correlations(
            start_date=args.correlation_start_date,
            end_date=args.correlation_end_date,
            force_refresh=not args.skip_theme_daily_refresh,
        )

    if not args.skip_pages:
        _rebuild_topic_pages()
        build_dashboard()
        print(f"dashboard={OUTPUT_HTML}")
        print(f"summary={OUTPUT_SUMMARY_MD}")
        print(f"leaderboard={OUTPUT_LEADERBOARD_MD}")


if __name__ == "__main__":
    main()

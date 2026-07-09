import argparse
import time
from typing import Optional

from sw_data_utils import cache_path, fetch_with_cache, get_pro


def get_trade_days(pro, start_date: str, end_date: str) -> list[str]:
    cal = fetch_with_cache(
        f"trade_cal_{start_date}_{end_date}",
        lambda: pro.trade_cal(exchange="SSE", start_date=start_date, end_date=end_date),
    )
    cal["is_open"] = cal["is_open"].astype(str)
    open_days = cal[cal["is_open"] == "1"].sort_values("cal_date")
    return open_days["cal_date"].astype(str).tolist()


def backfill_daily_market(
    start_date: str,
    end_date: str,
    max_new_fetches: Optional[int],
    sleep_seconds: int,
) -> int:
    pro = get_pro()
    trade_days = get_trade_days(pro, start_date=start_date, end_date=end_date)
    if not trade_days:
        raise RuntimeError("No trade days found in requested range.")

    fetched = 0
    for trade_date in trade_days:
        name = f"daily_market_{trade_date}"
        already_cached = cache_path(name).exists()
        try:
            fetch_with_cache(name, lambda trade_date=trade_date: pro.daily(trade_date=trade_date))
        except RuntimeError as exc:
            if "rate-limited" not in str(exc) or sleep_seconds <= 0:
                raise
            print(f"rate_limited date={trade_date}, sleeping {sleep_seconds}s before retry")
            time.sleep(sleep_seconds)
            fetch_with_cache(name, lambda trade_date=trade_date: pro.daily(trade_date=trade_date))
        except Exception:
            raise
        else:
            if already_cached:
                continue
            fetched += 1
            print(f"cached date={trade_date}")
            if max_new_fetches is not None and fetched >= max_new_fetches:
                break
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

    return fetched


def main() -> None:
    parser = argparse.ArgumentParser(description="回补全市场 daily 成交额历史缓存")
    parser.add_argument("--start-date", default="20240101", help="开始日期 YYYYMMDD")
    parser.add_argument("--end-date", default="20260630", help="结束日期 YYYYMMDD")
    parser.add_argument(
        "--max-new-fetches",
        type=int,
        default=1,
        help="本次最多抓取多少个新的 daily_market 缓存，默认 1",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=int,
        default=0,
        help="抓取之间等待秒数，默认 0",
    )
    args = parser.parse_args()

    fetched = backfill_daily_market(
        start_date=args.start_date,
        end_date=args.end_date,
        max_new_fetches=args.max_new_fetches,
        sleep_seconds=max(args.sleep_seconds, 0),
    )
    print(f"new_daily_market_fetches={fetched}")


if __name__ == "__main__":
    main()

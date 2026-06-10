import argparse
import os
import time
from pathlib import Path
from typing import Callable, Optional

import pandas as pd
import tushare as ts


for proxy_var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
    os.environ[proxy_var] = ""
    os.environ[proxy_var.lower()] = ""


ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / ".cache_scan_v2"
CACHE_DIR.mkdir(exist_ok=True)
MASTER_PATH = CACHE_DIR / "sw_daily_full_history.csv"


def get_pro():
    token = os.getenv("TUSHARE_TOKEN") or ts.get_token()
    if not token:
        raise RuntimeError("Missing TUSHARE_TOKEN. Configure it in env or Tushare local config.")
    return ts.pro_api(token)


def cache_path(name: str) -> Path:
    return CACHE_DIR / f"{name}.csv"


def save_df(df: pd.DataFrame, name: str) -> pd.DataFrame:
    df.to_csv(cache_path(name), index=False, encoding="utf-8-sig")
    return df


def load_df(name: str, dtype=None) -> Optional[pd.DataFrame]:
    path = cache_path(name)
    if not path.exists():
        return None
    return pd.read_csv(path, dtype=dtype)


def fetch_with_cache(name: str, fetcher: Callable[[], pd.DataFrame], dtype=None) -> pd.DataFrame:
    cached = load_df(name, dtype=dtype)
    if cached is not None:
        return cached
    try:
        df = fetcher()
        return save_df(df, name)
    except Exception as exc:
        if "频率超限" in str(exc):
            raise RuntimeError(
                f"{name} is rate-limited and has no local cache yet. Retry after the limit window. Original error: {exc}"
            )
        raise


def get_trade_days(pro, start_date: str, end_date: str) -> list[str]:
    cal = fetch_with_cache(
        f"trade_cal_{start_date}_{end_date}",
        lambda: pro.trade_cal(exchange="SSE", start_date=start_date, end_date=end_date),
    )
    cal["is_open"] = pd.to_numeric(cal["is_open"], errors="coerce")
    open_days = cal[cal["is_open"] == 1].sort_values("cal_date")
    return open_days["cal_date"].astype(str).tolist()


def get_sw_daily_chunk(pro, start_date: str, end_date: str) -> pd.DataFrame:
    df = fetch_with_cache(
        f"sw_daily_{start_date}_{end_date}",
        lambda: pro.sw_daily(start_date=start_date, end_date=end_date),
    )
    if df.empty:
        return df
    df["trade_date"] = df["trade_date"].astype(str)
    df["ts_code"] = df["ts_code"].astype(str)
    return df


def chunk_trade_days(trade_days: list[str], chunk_open_days: int) -> list[tuple[str, str]]:
    chunks: list[tuple[str, str]] = []
    for i in range(0, len(trade_days), chunk_open_days):
        days = trade_days[i : i + chunk_open_days]
        if days:
            chunks.append((days[0], days[-1]))
    return chunks


def load_master() -> pd.DataFrame:
    if not MASTER_PATH.exists():
        return pd.DataFrame()
    df = pd.read_csv(MASTER_PATH, dtype={"ts_code": str, "trade_date": str})
    return df


def save_master(df: pd.DataFrame) -> None:
    df = df.sort_values(["trade_date", "ts_code"]).drop_duplicates(
        subset=["ts_code", "trade_date"], keep="last"
    )
    df.to_csv(MASTER_PATH, index=False, encoding="utf-8-sig")


def merge_existing_chunk_caches(master: pd.DataFrame) -> pd.DataFrame:
    frames = [master] if not master.empty else []
    for path in CACHE_DIR.glob("sw_daily_*.csv"):
        if path.name == MASTER_PATH.name:
            continue
        chunk_df = pd.read_csv(path, dtype={"ts_code": str, "trade_date": str})
        if not chunk_df.empty:
            frames.append(chunk_df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def backfill_history(
    start_date: str,
    end_date: str,
    chunk_open_days: int,
    max_chunks: Optional[int],
    max_new_fetches: Optional[int],
    sleep_seconds: int,
) -> pd.DataFrame:
    pro = get_pro()
    trade_days = get_trade_days(pro, start_date=start_date, end_date=end_date)
    if not trade_days:
        raise RuntimeError("No trade days found in requested range.")

    chunks = chunk_trade_days(trade_days, chunk_open_days)
    if max_chunks is not None:
        chunks = chunks[:max_chunks]

    master = merge_existing_chunk_caches(load_master())
    existing_ranges = set()
    for path in CACHE_DIR.glob("sw_daily_*.csv"):
        if path.name == MASTER_PATH.name:
            continue
        stem = path.stem
        parts = stem.split("_")
        if len(parts) >= 4:
            existing_ranges.add((parts[2], parts[3]))

    fetched = 0
    for chunk_start, chunk_end in chunks:
        if (chunk_start, chunk_end) in existing_ranges:
            chunk_df = load_df(f"sw_daily_{chunk_start}_{chunk_end}", dtype={"ts_code": str, "trade_date": str})
        else:
            if max_new_fetches is not None and fetched >= max_new_fetches:
                break
            while True:
                try:
                    chunk_df = get_sw_daily_chunk(pro, chunk_start, chunk_end)
                    break
                except RuntimeError as exc:
                    if "rate-limited" not in str(exc) or sleep_seconds <= 0:
                        raise
                    print(f"rate_limited chunk={chunk_start}_{chunk_end}, sleeping {sleep_seconds}s before retry")
                    time.sleep(sleep_seconds)
            fetched += 1
            if sleep_seconds > 0 and fetched < len(chunks):
                print(f"fetched chunk={chunk_start}_{chunk_end}, sleeping {sleep_seconds}s before next chunk")
                time.sleep(sleep_seconds)
        if chunk_df is None or chunk_df.empty:
            continue
        master = pd.concat([master, chunk_df], ignore_index=True)

    if master.empty:
        raise RuntimeError("No sw_daily rows collected during backfill.")

    save_master(master)
    return master


def main() -> None:
    parser = argparse.ArgumentParser(description="回补申万行业日线长历史缓存")
    parser.add_argument("--start-date", default="20240101", help="开始日期 YYYYMMDD")
    parser.add_argument("--end-date", default="20260630", help="结束日期 YYYYMMDD")
    parser.add_argument(
        "--chunk-open-days",
        type=int,
        default=5,
        help="每个 sw_daily 请求覆盖的开市日数量，默认 5",
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=None,
        help="本次最多处理多少个分块，默认处理全部",
    )
    parser.add_argument(
        "--max-new-fetches",
        type=int,
        default=None,
        help="本次最多抓取多少个尚未缓存的新分块，默认不限制",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=int,
        default=65,
        help="新抓取分块之间的等待秒数，默认 65",
    )
    args = parser.parse_args()

    master = backfill_history(
        start_date=args.start_date,
        end_date=args.end_date,
        chunk_open_days=max(args.chunk_open_days, 1),
        max_chunks=args.max_chunks,
        max_new_fetches=args.max_new_fetches,
        sleep_seconds=max(args.sleep_seconds, 0),
    )
    print(f"master_rows={len(master)}")
    print(f"codes={master['ts_code'].nunique()}")
    print(f"dates={master['trade_date'].nunique()}")
    print(f"min_date={master['trade_date'].min()}")
    print(f"max_date={master['trade_date'].max()}")


if __name__ == "__main__":
    main()

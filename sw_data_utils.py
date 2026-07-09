import os
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

DEFAULT_END_DATE = "20260630"
YI_TO_TUSHARE_MV = 10000.0


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
        if "棰戠巼瓒呴檺" in str(exc):
            raise RuntimeError(
                f"{name} is rate-limited and has no local cache yet. Retry after the limit window. Original error: {exc}"
            )
        raise


def get_sw_daily(pro, start_date: str, end_date: str) -> pd.DataFrame:
    df = fetch_with_cache(
        f"sw_daily_{start_date}_{end_date}",
        lambda: pro.sw_daily(start_date=start_date, end_date=end_date),
    )
    for col in ["ts_code", "trade_date", "name"]:
        if col in df.columns:
            df[col] = df[col].astype(str)
    numeric_cols = ["close", "pct_change", "float_mv", "total_mv", "amount", "open", "high", "low"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def get_daily_basic(pro, trade_date: str) -> pd.DataFrame:
    df = fetch_with_cache(
        f"daily_basic_{trade_date}",
        lambda: pro.daily_basic(trade_date=trade_date, fields="ts_code,trade_date,total_mv,circ_mv"),
    )
    df["total_mv"] = pd.to_numeric(df["total_mv"], errors="coerce")
    if "circ_mv" in df.columns:
        df["circ_mv"] = pd.to_numeric(df["circ_mv"], errors="coerce")
    return df


def get_daily_market(pro, trade_date: str) -> pd.DataFrame:
    df = fetch_with_cache(
        f"daily_market_{trade_date}",
        lambda: pro.daily(trade_date=trade_date),
    )
    for col in ["close", "pre_close", "pct_chg", "amount"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def get_stock_daily_with_cache(pro, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    cache_name = f"daily_{ts_code}_{start_date}_{end_date}"
    cached = load_df(cache_name, dtype={"ts_code": str, "trade_date": str})
    if cached is None:
        df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        save_df(df, cache_name)
        cached = df

    if cached.empty:
        return cached

    cached["trade_date"] = cached["trade_date"].astype(str)
    for col in ["open", "high", "low", "close", "pre_close", "pct_chg", "amount"]:
        if col in cached.columns:
            cached[col] = pd.to_numeric(cached[col], errors="coerce")
    return cached.sort_values("trade_date").reset_index(drop=True)


def get_members_by_level(pro, index_code: str, level: str) -> pd.DataFrame:
    if level == "L1":
        return fetch_with_cache(f"index_member_all_l1_{index_code}", lambda: pro.index_member_all(l1_code=index_code), dtype=str)
    if level == "L2":
        return fetch_with_cache(f"index_member_all_l2_{index_code}", lambda: pro.index_member_all(l2_code=index_code), dtype=str)
    if level == "L3":
        return fetch_with_cache(f"index_member_all_l3_{index_code}", lambda: pro.index_member_all(l3_code=index_code), dtype=str)
    return pd.DataFrame()

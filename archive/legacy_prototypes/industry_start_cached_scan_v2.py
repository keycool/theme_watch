import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import tushare as ts


for proxy_var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
    os.environ[proxy_var] = ""
    os.environ[proxy_var.lower()] = ""


CACHE_DIR = Path(__file__).with_name(".cache_scan_v2")
CACHE_DIR.mkdir(exist_ok=True)


@dataclass
class ScanResult:
    industry_code: str
    industry_name: str
    latest_date: str
    convergence_ok: bool
    breakout_ok: bool
    leader_ok: bool
    score: int
    close: float
    ma250: float
    amount: float
    amount_ma20: float
    ret_120d: float
    ret_rank_pct: float
    leader_name: Optional[str]
    leader_limit_date: Optional[str]
    leader_follow_date: Optional[str]


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


def fetch_with_cache(name: str, fetcher, dtype=None) -> pd.DataFrame:
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


def latest_trade_dates(pro, end_date: str, lookback_days: int = 10) -> List[str]:
    end_ts = pd.to_datetime(end_date, format="%Y%m%d")
    start_date = (end_ts - pd.Timedelta(days=lookback_days)).strftime("%Y%m%d")
    cal = fetch_with_cache(
        f"trade_cal_{start_date}_{end_date}",
        lambda: pro.trade_cal(exchange="SSE", start_date=start_date, end_date=end_date),
    )
    cal["is_open"] = pd.to_numeric(cal["is_open"])
    open_days = cal[cal["is_open"] == 1].sort_values("cal_date")
    return open_days["cal_date"].tail(3).tolist()


def get_industries(pro) -> pd.DataFrame:
    df = fetch_with_cache(
        "sw_index_classify",
        lambda: pro.index_classify(src="SW2021"),
        dtype=str,
    )
    return df[df["level"] == "L1"][["index_code", "industry_name"]].drop_duplicates().copy()


def get_all_sw_daily(pro, start_date: str, end_date: str) -> pd.DataFrame:
    df = fetch_with_cache(
        f"sw_daily_{start_date}_{end_date}",
        lambda: pro.sw_daily(start_date=start_date, end_date=end_date),
    )
    numeric_cols = [
        "open",
        "high",
        "low",
        "close",
        "change",
        "pct_change",
        "vol",
        "amount",
        "pe",
        "pb",
        "float_mv",
        "total_mv",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)


def get_daily_basic(pro, trade_date: str) -> pd.DataFrame:
    df = fetch_with_cache(
        f"daily_basic_{trade_date}",
        lambda: pro.daily_basic(trade_date=trade_date, fields="ts_code,trade_date,total_mv,circ_mv"),
    )
    df["total_mv"] = pd.to_numeric(df["total_mv"], errors="coerce")
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


def get_stk_limit_all(pro, trade_date: str) -> pd.DataFrame:
    df = fetch_with_cache(
        f"stk_limit_{trade_date}",
        lambda: pro.stk_limit(start_date=trade_date, end_date=trade_date),
    )
    for col in ["up_limit", "down_limit"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def get_members(pro, industry_code: str) -> pd.DataFrame:
    return fetch_with_cache(
        f"index_member_all_{industry_code}",
        lambda: pro.index_member_all(l1_code=industry_code),
        dtype=str,
    )


def build_histories(all_sw_daily: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    histories: Dict[str, pd.DataFrame] = {}
    for ts_code, group in all_sw_daily.groupby("ts_code"):
        df = group.sort_values("trade_date").reset_index(drop=True).copy()
        df["ma250"] = df["close"].rolling(250).mean()
        df["amount_ma20"] = df["amount"].rolling(20).mean()
        histories[ts_code] = df
    return histories


def return_rank_pct(histories: Dict[str, pd.DataFrame]) -> Dict[str, float]:
    scores = {}
    for code, df in histories.items():
        if len(df) < 121:
            continue
        scores[code] = df.iloc[-1]["close"] / df.iloc[-121]["close"] - 1
    return pd.Series(scores).rank(pct=True).to_dict()


def convergence_rule(df: pd.DataFrame, rank_pct: float) -> Tuple[bool, float]:
    if len(df) < 121:
        return False, float("nan")
    last_120 = df.tail(120)
    first_80 = last_120.head(80)
    last_40 = last_120.tail(40)
    first_range = (first_80["high"].max() - first_80["low"].min()) / first_80["close"].mean()
    last_range = (last_40["high"].max() - last_40["low"].min()) / last_40["close"].mean()
    no_new_low = last_40["low"].min() >= last_120["low"].min() * 1.02
    range_contracts = last_range <= first_range * 0.90
    lagging = rank_pct <= 0.5
    ret_120d = last_120.iloc[-1]["close"] / last_120.iloc[0]["close"] - 1
    return bool(no_new_low and range_contracts and lagging), float(ret_120d)


def breakout_rule(df: pd.DataFrame) -> bool:
    if len(df) < 250:
        return False
    latest = df.iloc[-1]
    if pd.isna(latest["ma250"]) or pd.isna(latest["amount_ma20"]):
        return False
    return bool(
        latest["close"] >= latest["ma250"] * 1.03
        and latest["amount"] >= latest["amount_ma20"] * 1.20
    )


def leader_rule(
    pro,
    industry_code: str,
    daily_basic_df: pd.DataFrame,
    limit_df: pd.DataFrame,
    limit_market_df: pd.DataFrame,
    follow_market_df: pd.DataFrame,
) -> Tuple[bool, Optional[str]]:
    members = get_members(pro, industry_code)
    if members.empty:
        return False, None

    members = members[members["is_new"] == "Y"][["ts_code", "name"]].drop_duplicates()
    leaders = (
        members.merge(daily_basic_df[["ts_code", "total_mv"]], on="ts_code", how="inner")
        .sort_values("total_mv", ascending=False)
        .head(3)
    )
    if leaders.empty:
        return False, None

    prev_join = leaders.merge(limit_market_df[["ts_code", "close"]], on="ts_code", how="inner")
    prev_join = prev_join.merge(limit_df[["ts_code", "up_limit"]], on="ts_code", how="inner")
    if prev_join.empty:
        return False, None

    prev_join["hit_up_limit"] = prev_join["close"] >= prev_join["up_limit"] * 0.999
    hit = prev_join[prev_join["hit_up_limit"]]
    if hit.empty:
        return False, None

    leader = hit.iloc[0]
    follow_row = follow_market_df[follow_market_df["ts_code"] == leader["ts_code"]]
    if follow_row.empty:
        return False, None

    follow_ok = bool(follow_row.iloc[0]["close"] > leader["close"])
    return follow_ok, str(leader["name"])


def run_scan(end_date: str = "20260630") -> pd.DataFrame:
    pro = get_pro()
    dates = latest_trade_dates(pro, end_date=end_date)
    if len(dates) < 2:
        raise RuntimeError("Not enough recent trade dates for leader follow-through check.")

    latest_date = dates[-1]
    prev_date = dates[-2]
    latest_ts = pd.to_datetime(latest_date, format="%Y%m%d")
    start_date = (latest_ts - pd.Timedelta(days=420)).strftime("%Y%m%d")

    industries = get_industries(pro)
    sw_daily = get_all_sw_daily(pro, start_date=start_date, end_date=latest_date)
    histories = build_histories(sw_daily)
    ranks = return_rank_pct(histories)

    daily_basic_df = get_daily_basic(pro, prev_date)
    prev_market_df = get_daily_market(pro, prev_date)
    latest_market_df = get_daily_market(pro, latest_date)
    limit_df = get_stk_limit_all(pro, prev_date)

    results: List[ScanResult] = []
    for _, row in industries.iterrows():
        code = row["index_code"]
        name = row["industry_name"]
        history = histories.get(code)
        if history is None or history.empty:
            continue

        convergence_ok, ret_120d = convergence_rule(history, ranks.get(code, float("nan")))
        breakout_ok = breakout_rule(history)
        leader_ok, leader_name = leader_rule(
            pro,
            industry_code=code,
            daily_basic_df=daily_basic_df,
            limit_df=limit_df,
            limit_market_df=prev_market_df,
            follow_market_df=latest_market_df,
        )

        latest = history.iloc[-1]
        results.append(
            ScanResult(
                industry_code=code,
                industry_name=name,
                latest_date=latest_date,
                convergence_ok=convergence_ok,
                breakout_ok=breakout_ok,
                leader_ok=leader_ok,
                score=int(convergence_ok) + int(breakout_ok) + int(leader_ok),
                close=float(latest["close"]),
                ma250=float(latest["ma250"]) if pd.notna(latest["ma250"]) else float("nan"),
                amount=float(latest["amount"]),
                amount_ma20=float(latest["amount_ma20"]) if pd.notna(latest["amount_ma20"]) else float("nan"),
                ret_120d=float(ret_120d),
                ret_rank_pct=float(ranks.get(code, float("nan"))),
                leader_name=leader_name,
                leader_limit_date=prev_date if leader_name else None,
                leader_follow_date=latest_date if leader_name else None,
            )
        )

    return pd.DataFrame([r.__dict__ for r in results]).sort_values(
        ["score", "breakout_ok", "leader_ok", "convergence_ok"],
        ascending=[False, False, False, False],
    )


def main():
    df = run_scan()
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 30)
    print(df.head(15).to_string(index=False))


if __name__ == "__main__":
    main()

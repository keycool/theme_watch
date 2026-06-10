import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import tushare as ts


for proxy_var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
    # The current shell session may inject a dead local proxy.
    os.environ[proxy_var] = ""
    os.environ[proxy_var.lower()] = ""


CACHE_DIR = Path(__file__).with_name(".cache")
CACHE_DIR.mkdir(exist_ok=True)


@dataclass
class IndustryResult:
    industry_code: str
    industry_name: str
    latest_date: str
    condition_convergence: bool
    condition_breakout: bool
    condition_leader: bool
    score: int
    latest_close: float
    ma250: float
    volume: float
    volume_ma20: float
    return_120d_pct: float
    return_120d_rank_pct: float
    breakout_leader: Optional[str]
    leader_next_day_ok: Optional[bool]


def get_pro():
    token = os.getenv("TUSHARE_TOKEN") or ts.get_token()
    if not token:
        raise RuntimeError("Missing TUSHARE_TOKEN. Configure it in env or Tushare local config.")
    return ts.pro_api(token)


def cache_csv_path(name: str) -> Path:
    return CACHE_DIR / f"{name}.csv"


def save_cache(df: pd.DataFrame, name: str) -> pd.DataFrame:
    path = cache_csv_path(name)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return df


def load_cache(name: str) -> Optional[pd.DataFrame]:
    path = cache_csv_path(name)
    if not path.exists():
        return None
    return pd.read_csv(path, dtype=str)


def read_typed_cache(name: str) -> Optional[pd.DataFrame]:
    path = cache_csv_path(name)
    if not path.exists():
        return None
    return pd.read_csv(path)


def latest_trade_date(pro, start_date: str, end_date: str) -> str:
    cal = pro.trade_cal(exchange="SSE", start_date=start_date, end_date=end_date)
    open_days = cal[cal["is_open"] == 1].sort_values("cal_date")
    if open_days.empty:
        raise RuntimeError("No open trade date found in range.")
    return str(open_days.iloc[-1]["cal_date"])


def get_ths_industries(pro) -> pd.DataFrame:
    cached = load_cache("ths_index_A_I")
    if cached is not None:
        return cached
    rows = [
        {"ts_code": "700305.TI", "name": "日常消费品(A股)"},
        {"ts_code": "700306.TI", "name": "医疗保健(A股)"},
        {"ts_code": "700307.TI", "name": "金融(A股)"},
        {"ts_code": "700308.TI", "name": "信息技术(A股)"},
    ]
    return pd.DataFrame(rows)


def get_ths_members(pro, industry_code: str) -> pd.DataFrame:
    cached = load_cache(f"ths_member_{industry_code}")
    if cached is not None:
        return cached
    df = pro.ths_member(ts_code=industry_code)
    return save_cache(df, f"ths_member_{industry_code}")


def get_ths_history(pro, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    cache_name = f"ths_daily_{ts_code}_{start_date}_{end_date}"
    cached = read_typed_cache(cache_name)
    if cached is not None:
        df = cached
    else:
        df = pro.ths_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        save_cache(df, cache_name)

    if df.empty:
        return df

    df = df.sort_values("trade_date").reset_index(drop=True)
    df["close"] = pd.to_numeric(df["close"])
    df["high"] = pd.to_numeric(df["high"])
    df["low"] = pd.to_numeric(df["low"])
    df["vol"] = pd.to_numeric(df["vol"])
    df["ma250"] = df["close"].rolling(250).mean()
    df["vol_ma20"] = df["vol"].rolling(20).mean()
    return df


def get_daily_basic_on_date(pro, trade_date: str) -> pd.DataFrame:
    cache_name = f"daily_basic_{trade_date}"
    cached = read_typed_cache(cache_name)
    if cached is not None:
        df = cached
    else:
        df = pro.daily_basic(trade_date=trade_date, fields="ts_code,trade_date,total_mv,circ_mv")
        save_cache(df, cache_name)

    if df.empty:
        return df

    df["total_mv"] = pd.to_numeric(df["total_mv"])
    df["circ_mv"] = pd.to_numeric(df["circ_mv"])
    return df


def get_limit_up_on_date(pro, trade_date: str) -> pd.DataFrame:
    cache_name = f"limit_list_d_{trade_date}"
    cached = load_cache(cache_name)
    if cached is not None:
        return cached
    df = pro.limit_list_d(trade_date=trade_date)
    return save_cache(df, cache_name)


def get_stock_daily(pro, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    cache_name = f"daily_{ts_code}_{start_date}_{end_date}"
    cached = read_typed_cache(cache_name)
    if cached is not None:
        df = cached
    else:
        df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        save_cache(df, cache_name)

    if df.empty:
        return df

    df["close"] = pd.to_numeric(df["close"])
    df = df.sort_values("trade_date").reset_index(drop=True)
    return df


def compute_return_ranks(histories: Dict[str, pd.DataFrame]) -> Dict[str, float]:
    rows: List[Tuple[str, float]] = []
    for code, df in histories.items():
        if len(df) < 121:
            continue
        ret = df.iloc[-1]["close"] / df.iloc[-121]["close"] - 1
        rows.append((code, ret))
    series = pd.Series({code: ret for code, ret in rows})
    return series.rank(pct=True).to_dict()


def convergence_rule(df: pd.DataFrame, return_rank_pct: float) -> Tuple[bool, float]:
    if len(df) < 121:
        return False, float("nan")

    last_120 = df.tail(120).copy()
    first_80 = last_120.head(80)
    last_40 = last_120.tail(40)

    first_80_range = (first_80["high"].max() - first_80["low"].min()) / first_80["close"].mean()
    last_40_range = (last_40["high"].max() - last_40["low"].min()) / last_40["close"].mean()
    no_new_low = last_40["low"].min() >= last_120["low"].min() * 1.02
    range_contracts = last_40_range <= first_80_range * 0.90
    lagging_rank = return_rank_pct <= 0.5
    ret_120 = last_120.iloc[-1]["close"] / last_120.iloc[0]["close"] - 1

    return bool(no_new_low and range_contracts and lagging_rank), ret_120


def breakout_rule(df: pd.DataFrame) -> bool:
    if len(df) < 250:
        return False
    latest = df.iloc[-1]
    if pd.isna(latest["ma250"]) or pd.isna(latest["vol_ma20"]):
        return False
    return bool(
        latest["close"] >= latest["ma250"] * 1.03
        and latest["vol"] >= latest["vol_ma20"] * 1.20
    )


def pick_member_columns(df: pd.DataFrame) -> pd.DataFrame:
    code_col = "code" if "code" in df.columns else "ts_code"
    name_col = "name"
    out = df[[code_col, name_col]].drop_duplicates().copy()
    if code_col == "code":
        out = out.rename(columns={"code": "ts_code"})
        out["ts_code"] = out["ts_code"].astype(str).str.zfill(6)
        out["ts_code"] = out["ts_code"].apply(
            lambda x: f"{x}.SH" if x.startswith(("5", "6", "9")) else f"{x}.SZ"
        )
    return out


def leader_rule(pro, industry_code: str, trade_date: str) -> Tuple[bool, Optional[str], Optional[bool]]:
    members = get_ths_members(pro, industry_code)
    if members.empty:
        return False, None, None
    members = pick_member_columns(members)

    daily_basic = get_daily_basic_on_date(pro, trade_date)
    merged = members.merge(daily_basic, on="ts_code", how="inner")
    if merged.empty:
        return False, None, None

    leaders = merged.sort_values("total_mv", ascending=False).head(3)

    limit_df = get_limit_up_on_date(pro, trade_date)
    up_limits = limit_df[limit_df["limit"] == "U"][["ts_code"]].drop_duplicates()
    hit = leaders.merge(up_limits, on="ts_code", how="inner")
    if hit.empty:
        return False, None, None

    leader_code = hit.iloc[0]["ts_code"]
    leader_name = hit.iloc[0]["name"]

    daily = get_stock_daily(pro, leader_code, start_date="20260520", end_date="20260610")
    if daily.empty:
        return True, leader_name, None

    idx = daily.index[daily["trade_date"] == trade_date].tolist()
    if not idx or idx[0] == len(daily) - 1:
        return True, leader_name, None

    next_day_ok = bool(daily.iloc[idx[0] + 1]["close"] > daily.iloc[idx[0]]["close"])
    return True, leader_name, next_day_ok


def evaluate_industry(pro, industry_code: str, industry_name: str, latest_date: str, return_rank_pct: float) -> Optional[IndustryResult]:
    history = get_ths_history(pro, industry_code, start_date="20240101", end_date=latest_date)
    if history.empty:
        return None

    convergence_ok, ret_120 = convergence_rule(history, return_rank_pct)
    breakout_ok = breakout_rule(history)
    leader_ok, leader_name, leader_next_day_ok = leader_rule(pro, industry_code, latest_date)

    latest = history.iloc[-1]
    score = int(convergence_ok) + int(breakout_ok) + int(leader_ok)

    return IndustryResult(
        industry_code=industry_code,
        industry_name=industry_name,
        latest_date=str(latest["trade_date"]),
        condition_convergence=convergence_ok,
        condition_breakout=breakout_ok,
        condition_leader=leader_ok,
        score=score,
        latest_close=float(latest["close"]),
        ma250=float(latest["ma250"]) if pd.notna(latest["ma250"]) else float("nan"),
        volume=float(latest["vol"]),
        volume_ma20=float(latest["vol_ma20"]) if pd.notna(latest["vol_ma20"]) else float("nan"),
        return_120d_pct=float(ret_120),
        return_120d_rank_pct=float(return_rank_pct),
        breakout_leader=leader_name,
        leader_next_day_ok=leader_next_day_ok,
    )


def main():
    pro = get_pro()
    latest_date = latest_trade_date(pro, start_date="20260501", end_date="20260630")

    industries = get_ths_industries(pro)
    sample = industries.copy()

    histories: Dict[str, pd.DataFrame] = {}
    for _, row in sample.iterrows():
        histories[row["ts_code"]] = get_ths_history(
            pro,
            ts_code=row["ts_code"],
            start_date="20240101",
            end_date=latest_date,
        )
        time.sleep(1)

    return_ranks = compute_return_ranks(histories)

    results: List[IndustryResult] = []
    for _, row in sample.iterrows():
        result = evaluate_industry(
            pro,
            industry_code=row["ts_code"],
            industry_name=row["name"],
            latest_date=latest_date,
            return_rank_pct=return_ranks.get(row["ts_code"], float("nan")),
        )
        if result:
            results.append(result)
        time.sleep(1)

    if not results:
        print("No results generated.")
        return

    df = pd.DataFrame([r.__dict__ for r in results]).sort_values(
        ["score", "condition_breakout", "condition_leader"],
        ascending=[False, False, False],
    )
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 30)
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()

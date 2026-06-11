from typing import Optional

import pandas as pd

from industry_start_strategy_v1_engine import StrategyInputs


def _safe_bool(value: Optional[bool]) -> Optional[bool]:
    return None if value is None else bool(value)


def rolling_range(df: pd.DataFrame) -> float:
    return float((df["high"].max() - df["low"].min()) / df["close"].mean())


def build_histories(sw_daily: pd.DataFrame) -> dict[str, pd.DataFrame]:
    histories: dict[str, pd.DataFrame] = {}
    for code, group in sw_daily.groupby("ts_code"):
        hist = group.sort_values("trade_date").reset_index(drop=True).copy()
        hist["close"] = pd.to_numeric(hist["close"], errors="coerce")
        hist["high"] = pd.to_numeric(hist["high"], errors="coerce")
        hist["low"] = pd.to_numeric(hist["low"], errors="coerce")
        hist["amount"] = pd.to_numeric(hist["amount"], errors="coerce")
        hist["ma250"] = hist["close"].rolling(250).mean()
        hist["amount_ma20"] = hist["amount"].rolling(20).mean()
        histories[code] = hist
    return histories


def compute_ret_120d_ranks(histories: dict[str, pd.DataFrame]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for code, hist in histories.items():
        if len(hist) < 121:
            continue
        scores[code] = float(hist.iloc[-1]["close"] / hist.iloc[-121]["close"] - 1)
    if not scores:
        return {}
    return pd.Series(scores).rank(pct=True).to_dict()


def build_strategy_input(
    row: pd.Series,
    history: pd.DataFrame,
    ret_120d_rank_pct: Optional[float],
    leader_snapshot: Optional[dict],
) -> StrategyInputs:
    latest = history.iloc[-1]
    latest_close = float(latest["close"])
    latest_amount = float(latest["amount"])

    ma250 = float(latest["ma250"]) if pd.notna(latest["ma250"]) else None
    amount_ma20 = float(latest["amount_ma20"]) if pd.notna(latest["amount_ma20"]) else None

    ret_120d = None
    close_to_120d_high_ratio = None
    close_120d_high = None
    close_120d_low = None
    close_40d_low = None
    range_first_80 = None
    range_last_40 = None
    if len(history) >= 121:
        last_120 = history.tail(120).copy()
        first_80 = last_120.head(80)
        last_40 = last_120.tail(40)
        ret_120d = float(last_120.iloc[-1]["close"] / last_120.iloc[0]["close"] - 1)
        close_120d_high = float(last_120["close"].max())
        close_120d_low = float(last_120["close"].min())
        close_40d_low = float(last_40["close"].min())
        close_to_120d_high_ratio = float(latest_close / close_120d_high) if close_120d_high else None
        range_first_80 = rolling_range(first_80)
        range_last_40 = rolling_range(last_40)

    recent_2d_above_ma250 = None
    if len(history) >= 2 and history["ma250"].notna().tail(2).all():
        recent_2d_above_ma250 = bool((history.tail(2)["close"] >= history.tail(2)["ma250"]).all())

    above_ma250_3pct_streak = None
    if history["ma250"].notna().any():
        streak = 0
        for _, hist_row in history.sort_values("trade_date").iloc[::-1].iterrows():
            ma250_value = hist_row.get("ma250")
            close_value = hist_row.get("close")
            if pd.isna(ma250_value) or pd.isna(close_value):
                break
            if float(close_value) >= float(ma250_value) * 1.03:
                streak += 1
            else:
                break
        above_ma250_3pct_streak = streak

    local_activity_ok = None
    if len(history) >= 5:
        recent_5 = history.tail(5)
        amount_ma5 = recent_5["amount"].mean()
        ret_5d = recent_5.iloc[-1]["close"] / recent_5.iloc[0]["close"] - 1
        local_activity_ok = bool(ret_5d > 0.02 or latest_amount >= amount_ma5 * 1.10)

    leader_count = None
    leader_top1_name = None
    leader_top1_pct_change = None
    leader_top1_above_ma60 = None
    leader_top1_above_ma250 = None
    leader_follow_ok = None
    leader_5d_rank_pct = None
    if leader_snapshot:
        leader_count = leader_snapshot.get("leader_count")
        leader_top1_name = leader_snapshot.get("leader_top1_name")
        leader_top1_pct_change = leader_snapshot.get("leader_top1_pct_change")
        leader_top1_above_ma60 = leader_snapshot.get("leader_top1_above_ma60")
        leader_top1_above_ma250 = leader_snapshot.get("leader_top1_above_ma250")
        leader_follow_ok = leader_snapshot.get("leader_follow_ok")
        leader_5d_rank_pct = leader_snapshot.get("leader_5d_rank_pct")

    return StrategyInputs(
        industry_code=str(row["industry_code"]),
        industry_name=str(row["industry_name"]),
        latest_close=latest_close,
        ma250=ma250,
        ret_120d=ret_120d,
        ret_120d_rank_pct=ret_120d_rank_pct,
        close_to_120d_high_ratio=close_to_120d_high_ratio,
        leaders_above_ma60_ratio=None,
        leaders_above_ma250_ratio=None,
        close_120d_high=close_120d_high,
        close_120d_low=close_120d_low,
        close_40d_low=close_40d_low,
        range_first_80=range_first_80,
        range_last_40=range_last_40,
        amount_latest=latest_amount,
        amount_ma20=amount_ma20,
        recent_2d_above_ma250=_safe_bool(recent_2d_above_ma250),
        above_ma250_3pct_streak=above_ma250_3pct_streak,
        leader_count=leader_count,
        leader_top1_name=leader_top1_name,
        leader_top1_pct_change=leader_top1_pct_change,
        leader_top1_above_ma60=_safe_bool(leader_top1_above_ma60),
        leader_top1_above_ma250=_safe_bool(leader_top1_above_ma250),
        leader_5d_rank_pct=leader_5d_rank_pct,
        leader_follow_ok=_safe_bool(leader_follow_ok),
        leaders_above_ma60_count=None,
        leaders_above_ma250_count=None,
        local_activity_ok=_safe_bool(local_activity_ok),
    )

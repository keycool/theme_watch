import json
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

import pandas as pd

from build_sw_l1_sample_pool import DEFAULT_END_DATE, build_sample_pool, get_pro, get_sw_daily
from industry_start_cached_scan_v2 import get_daily_basic, get_daily_market, get_members
from industry_start_strategy_v1_engine import StrategyInputs, evaluate_strategy


ROOT = Path(__file__).resolve().parent
GENERATED_INPUT_DIR = ROOT / "generated_strategy_inputs"
GENERATED_INPUT_DIR.mkdir(exist_ok=True)
OUTPUT_CSV = ROOT / "sw_l1_strategy_scan.csv"
OUTPUT_MD = ROOT / "sw_l1_strategy_scan_summary.md"
MASTER_HISTORY_PATH = ROOT / ".cache_scan_v2" / "sw_daily_full_history.csv"


def _safe_bool(value: Optional[bool]) -> Optional[bool]:
    return None if value is None else bool(value)


def _rolling_range(df: pd.DataFrame) -> float:
    return float((df["high"].max() - df["low"].min()) / df["close"].mean())


def _build_histories(sw_daily: pd.DataFrame) -> dict[str, pd.DataFrame]:
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


def _load_sw_history(pro, end_date: str) -> pd.DataFrame:
    if MASTER_HISTORY_PATH.exists():
        df = pd.read_csv(MASTER_HISTORY_PATH, dtype={"ts_code": str, "trade_date": str})
        if not df.empty:
            return df
    df = get_sw_daily(pro, start_date="20250506", end_date=end_date)
    df["trade_date"] = df["trade_date"].astype(str)
    return df


def _compute_ret_120d_ranks(histories: dict[str, pd.DataFrame]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for code, hist in histories.items():
        if len(hist) < 121:
            continue
        scores[code] = float(hist.iloc[-1]["close"] / hist.iloc[-121]["close"] - 1)
    if not scores:
        return {}
    return pd.Series(scores).rank(pct=True).to_dict()


def _build_strategy_input(
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
        close_to_120d_high_ratio = (
            float(latest_close / close_120d_high) if close_120d_high else None
        )
        range_first_80 = _rolling_range(first_80)
        range_last_40 = _rolling_range(last_40)

    recent_2d_above_ma250 = None
    if len(history) >= 2 and history["ma250"].notna().tail(2).all():
        recent_2d_above_ma250 = bool((history.tail(2)["close"] >= history.tail(2)["ma250"]).all())

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


def _write_generated_input(inputs: StrategyInputs) -> None:
    path = GENERATED_INPUT_DIR / f"{inputs.industry_code}.json"
    path.write_text(json.dumps(asdict(inputs), ensure_ascii=False, indent=2), encoding="utf-8")


def _get_stock_daily_with_cache(pro, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    cache_name = f"daily_{ts_code}_{start_date}_{end_date}"
    cache_path = ROOT / ".cache_scan_v2" / f"{cache_name}.csv"
    if cache_path.exists():
        df = pd.read_csv(cache_path, dtype={"ts_code": str, "trade_date": str})
    else:
        df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        df.to_csv(cache_path, index=False, encoding="utf-8-sig")

    if df.empty:
        return df

    df["trade_date"] = df["trade_date"].astype(str)
    for col in ["open", "high", "low", "close", "pre_close", "pct_chg", "amount"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values("trade_date").reset_index(drop=True)


def _build_leader_snapshots(pro, latest_date: str, industry_codes: List[str]) -> dict[str, dict]:
    latest_basic = get_daily_basic(pro, latest_date)
    latest_market = get_daily_market(pro, latest_date)
    latest_basic["total_mv"] = pd.to_numeric(latest_basic["total_mv"], errors="coerce")
    latest_market["pct_chg"] = pd.to_numeric(latest_market["pct_chg"], errors="coerce")

    snapshots: dict[str, dict] = {}
    for code in industry_codes:
        members = get_members(pro, code)
        if members.empty:
            continue
        members = members[members["is_new"] == "Y"][["ts_code", "name"]].drop_duplicates()
        leaders = (
            members.merge(latest_basic[["ts_code", "total_mv"]], on="ts_code", how="inner")
            .sort_values("total_mv", ascending=False)
            .head(3)
        )
        if leaders.empty:
            continue
        leader_top1 = leaders.iloc[0]
        market_row = latest_market[latest_market["ts_code"] == leader_top1["ts_code"]]
        top1_pct = None if market_row.empty else float(market_row.iloc[0]["pct_chg"])
        daily = _get_stock_daily_with_cache(
            pro,
            ts_code=str(leader_top1["ts_code"]),
            start_date="20240101",
            end_date=latest_date,
        )
        above_ma60 = None
        above_ma250 = None
        follow_ok = None
        leader_5d_rank_pct = None
        if not daily.empty:
            daily["ma60"] = daily["close"].rolling(60).mean()
            daily["ma250"] = daily["close"].rolling(250).mean()
            last = daily.iloc[-1]
            if pd.notna(last["ma60"]):
                above_ma60 = bool(last["close"] >= last["ma60"])
            if pd.notna(last["ma250"]):
                above_ma250 = bool(last["close"] >= last["ma250"])
            if len(daily) >= 2:
                follow_ok = bool(daily.iloc[-1]["close"] > daily.iloc[-2]["close"])
            if len(daily) >= 6:
                leader_5d_rank_pct = float(daily.iloc[-1]["close"] / daily.iloc[-6]["close"] - 1)
        snapshots[code] = {
            "leader_count": int(len(leaders)),
            "leader_top1_name": str(leader_top1["name"]),
            "leader_top1_pct_change": top1_pct,
            "leader_top1_above_ma60": above_ma60,
            "leader_top1_above_ma250": above_ma250,
            "leader_follow_ok": follow_ok,
            "leader_5d_rank_pct": leader_5d_rank_pct,
        }
    return snapshots


def run_scan(end_date: str = DEFAULT_END_DATE, min_total_mv_yi: float = 5000.0) -> pd.DataFrame:
    sample_pool = build_sample_pool(end_date=end_date, threshold_yi=min_total_mv_yi)
    pool = sample_pool[sample_pool["passes_total_mv_gate"]].copy().reset_index(drop=True)

    pro = get_pro()
    sw_daily = _load_sw_history(pro, end_date=end_date)
    histories = _build_histories(sw_daily)
    ret_120d_ranks = _compute_ret_120d_ranks(histories)
    leader_snapshots = _build_leader_snapshots(pro, str(pool["latest_date"].iloc[0]), pool["industry_code"].tolist())

    rows: List[dict] = []
    for _, row in pool.iterrows():
        code = str(row["industry_code"])
        history = histories.get(code)
        if history is None or history.empty:
            continue

        inputs = _build_strategy_input(row, history, ret_120d_ranks.get(code), leader_snapshots.get(code))
        _write_generated_input(inputs)
        evaluation = evaluate_strategy(inputs)

        rows.append(
            {
                "industry_code": evaluation.industry_code,
                "industry_name": evaluation.industry_name,
                "latest_date": row["latest_date"],
                "total_mv_yi": row["total_mv_yi"],
                "prefilter_label": evaluation.prefilter_label,
                "final_label": evaluation.final_label,
                "summary_line": evaluation.summary_line,
                "prefilter_hit_count": evaluation.prefilter_hit_count,
                "structure_score": evaluation.structure_score,
                "breakout_emerged": evaluation.breakout_emerged,
                "breakout_confirmed": evaluation.breakout_confirmed,
                "leader_turning_strong_ok": evaluation.leader_turning_strong_ok,
                "leader_confirmed_ok": evaluation.leader_confirmed_ok,
                "leader_count": inputs.leader_count,
                "leader_top1_name": inputs.leader_top1_name,
                "leader_top1_pct_change": inputs.leader_top1_pct_change,
                "leader_top1_above_ma60": inputs.leader_top1_above_ma60,
                "leader_top1_above_ma250": inputs.leader_top1_above_ma250,
                "leader_follow_ok": inputs.leader_follow_ok,
                "leader_5d_rank_pct": inputs.leader_5d_rank_pct,
                "local_activity_ok": inputs.local_activity_ok,
                "has_ma250": inputs.ma250 is not None,
                "has_amount_ma20": inputs.amount_ma20 is not None,
                "has_ret_120d_rank": inputs.ret_120d_rank_pct is not None,
                "note": "已补龙头强度、趋势位置与持续性字段",
            }
        )

    return pd.DataFrame(rows).sort_values(
        ["prefilter_label", "final_label", "total_mv_yi"],
        ascending=[True, True, False],
    )


def write_summary(df: pd.DataFrame) -> None:
    final_counts = df["final_label"].value_counts(dropna=False).to_dict()
    prefilter_counts = df["prefilter_label"].value_counts(dropna=False).to_dict()

    lines = [
        "# 申万一级行业预扫描结果",
        "",
        "- 这是第一版自动扫描链路结果。",
        "- 当前只接入了板块层字段，龙头确认字段仍为空。",
        "- 因此结果应视为 `预扫描 / 粗筛`，不应直接当成最终行业结论。",
        "",
        "## 分流统计",
        "",
    ]

    for label, count in prefilter_counts.items():
        lines.append(f"- `{label}`：`{count}`")

    lines.extend(["", "## 标签统计", ""])
    for label, count in final_counts.items():
        lines.append(f"- `{label}`：`{count}`")

    lines.extend(["", "## 样例输出", ""])
    for _, row in df.head(15).iterrows():
        lines.append(
            f"- `{row['industry_name']}` `{row['industry_code']}`：`{row['final_label']}`，{row['summary_line']}"
        )

    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    df = run_scan()
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    write_summary(df)
    pd.set_option("display.width", 240)
    pd.set_option("display.max_columns", 30)
    print(df.head(20).to_string(index=False))


if __name__ == "__main__":
    main()

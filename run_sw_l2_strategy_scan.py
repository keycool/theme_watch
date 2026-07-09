from dataclasses import asdict
import json
from pathlib import Path
from typing import List, Optional

import pandas as pd

from build_sw_l2_focus_leaderboard import build_leader_snapshots_l2, load_classify
from build_sw_l2_sample_pool import DEFAULT_THRESHOLD_YI, build_sample_pool
from industry_start_strategy_v1_engine import StrategyInputs, evaluate_strategy
from strategy_scan_common import build_histories, build_strategy_input, compute_ret_120d_ranks
from sw_data_utils import DEFAULT_END_DATE, get_daily_market, get_pro


ROOT = Path(__file__).resolve().parent
MASTER_HISTORY_PATH = ROOT / ".cache_scan_v2" / "sw_daily_full_history.csv"
GENERATED_INPUT_DIR = ROOT / "generated_strategy_inputs_l2"
GENERATED_INPUT_DIR.mkdir(exist_ok=True)
OUTPUT_CSV = ROOT / "sw_l2_strategy_scan.csv"
OUTPUT_SUMMARY_MD = ROOT / "sw_l2_strategy_scan_summary.md"
OUTPUT_LEADERBOARD_MD = ROOT / "sw_l2_strategy_leaderboard.md"

GROUP_ORDER = [
    "趋势延续型强势",
    "趋势延续型偏强",
    "接近启动",
    "启动确认",
    "早期启动",
    "观察中",
    "未启动",
]


def _write_generated_input(inputs: StrategyInputs) -> None:
    path = GENERATED_INPUT_DIR / f"{inputs.industry_code}.json"
    path.write_text(json.dumps(asdict(inputs), ensure_ascii=False, indent=2), encoding="utf-8")


def _load_history() -> pd.DataFrame:
    return pd.read_csv(MASTER_HISTORY_PATH, dtype={"ts_code": str, "trade_date": str})


def _build_market_amount_history(pro, trade_dates: List[str]) -> dict[str, float]:
    market_amount_history: dict[str, float] = {}
    for trade_date in trade_dates:
        try:
            market_df = get_daily_market(pro, trade_date)
        except Exception:
            continue
        if market_df.empty or "amount" not in market_df.columns:
            continue
        market_amount = pd.to_numeric(market_df["amount"], errors="coerce").sum()
        if pd.notna(market_amount) and market_amount > 0:
            market_amount_history[str(trade_date)] = float(market_amount)
    return market_amount_history


def _build_crowding_snapshot(
    history: pd.DataFrame,
    market_amount_history: dict[str, float],
    leader_snapshot: Optional[dict],
) -> dict:
    series_rows: List[dict] = []
    for _, row in history.iterrows():
        trade_date = str(row["trade_date"])
        market_amount = market_amount_history.get(trade_date)
        industry_amount = pd.to_numeric(row.get("amount"), errors="coerce")
        if market_amount is None or pd.isna(industry_amount) or market_amount <= 0:
            continue
        series_rows.append(
            {
                "trade_date": trade_date,
                "industry_amount": float(industry_amount),
                "market_amount": float(market_amount),
                "absorption_rate": float(industry_amount) / float(market_amount),
            }
        )

    if not series_rows:
        return {
            "industry_amount": None,
            "market_amount": None,
            "absorption_rate": None,
            "absorption_rate_rank_pct": None,
            "absorption_rate_5d_change": None,
            "crowding_label": "数据不足",
            "crowding_note": "缺少可用的全市场成交额历史，暂不判断拥挤度。",
        }

    crowding_df = pd.DataFrame(series_rows).sort_values("trade_date").reset_index(drop=True)
    latest = crowding_df.iloc[-1]
    latest_absorption_rate = float(latest["absorption_rate"])
    rank_pct = float(crowding_df["absorption_rate"].rank(pct=True).iloc[-1])

    absorption_rate_5d_change = None
    if len(crowding_df) >= 6:
        absorption_rate_5d_change = float(
            crowding_df.iloc[-1]["absorption_rate"] - crowding_df.iloc[-6]["absorption_rate"]
        )

    leader_follow_ok = None if not leader_snapshot else leader_snapshot.get("leader_follow_ok")
    leader_top1_pct_change = None if not leader_snapshot else leader_snapshot.get("leader_top1_pct_change")
    leader_top1_above_ma60 = None if not leader_snapshot else leader_snapshot.get("leader_top1_above_ma60")
    leader_active_count = None if not leader_snapshot else leader_snapshot.get("leader_active_count")
    leader_count = None if not leader_snapshot else leader_snapshot.get("leader_count")
    leaders_above_ma60_ratio = None if not leader_snapshot else leader_snapshot.get("leaders_above_ma60_ratio")

    retreat_signals = [
        leader_follow_ok is False,
        leader_top1_pct_change is not None and leader_top1_pct_change <= 0,
        leader_top1_above_ma60 is False,
        leader_count not in (None, 0) and leader_active_count == 0,
        leaders_above_ma60_ratio is not None and leaders_above_ma60_ratio < 0.5,
        absorption_rate_5d_change is not None and absorption_rate_5d_change <= 0,
    ]
    retreat_signal_count = sum(bool(signal) for signal in retreat_signals)

    if len(crowding_df) < 20:
        crowding_label = "数据不足"
        crowding_note = "吸筹率历史样本不足 20 个交易日，先不做稳定拥挤判断。"
    elif rank_pct >= 0.99 and retreat_signal_count >= 1:
        crowding_label = "过热退潮"
        crowding_note = "吸筹率已处极高分位，同时出现龙头或成交拥挤退潮信号。"
    elif rank_pct >= 0.95:
        crowding_label = "过热预警"
        crowding_note = "吸筹率处于高分位，追高容错率下降。"
    elif rank_pct >= 0.80:
        crowding_label = "拥挤偏高"
        crowding_note = "吸筹率已偏高，后续需要观察是否继续缩圈。"
    else:
        crowding_label = "拥挤正常"
        crowding_note = "吸筹率未进入明显拥挤区间。"

    return {
        "industry_amount": float(latest["industry_amount"]),
        "market_amount": float(latest["market_amount"]),
        "absorption_rate": latest_absorption_rate,
        "absorption_rate_rank_pct": rank_pct,
        "absorption_rate_5d_change": absorption_rate_5d_change,
        "crowding_label": crowding_label,
        "crowding_note": crowding_note,
    }


def run_scan(end_date: str, min_total_mv_yi: float) -> pd.DataFrame:
    sample_pool = build_sample_pool(end_date=end_date, threshold_yi=min_total_mv_yi)
    pool = sample_pool[sample_pool["passes_total_mv_gate"]].copy().reset_index(drop=True)
    if pool.empty:
        return pd.DataFrame()

    classify_df = load_classify()
    history_df = _load_history()
    histories = build_histories(history_df)
    ret_120d_ranks = compute_ret_120d_ranks(histories)
    pro = get_pro()

    latest_date = str(pool["latest_date"].dropna().iloc[0])
    leader_snapshots = build_leader_snapshots_l2(
        pro=pro,
        latest_date=latest_date,
        classify_df=classify_df,
        industry_codes=pool["industry_code"].dropna().astype(str).tolist(),
    )

    trade_dates = sorted(history_df["trade_date"].dropna().astype(str).unique().tolist())[-252:]
    market_amount_history = _build_market_amount_history(pro, trade_dates)

    rows: List[dict] = []
    for _, row in pool.iterrows():
        code = str(row["industry_code"])
        history = histories.get(code)
        if history is None or history.empty:
            continue

        leader_snapshot = leader_snapshots.get(code)
        inputs = build_strategy_input(row, history, ret_120d_ranks.get(code), leader_snapshot)
        _write_generated_input(inputs)
        evaluation = evaluate_strategy(inputs)
        crowding = _build_crowding_snapshot(history.tail(252), market_amount_history, leader_snapshot)

        rows.append(
            {
                "l1_name": row["l1_name"],
                "industry_code": evaluation.industry_code,
                "industry_name": evaluation.industry_name,
                "latest_date": row["latest_date"],
                "total_mv_yi": row["total_mv_yi"],
                "prefilter_label": evaluation.prefilter_label,
                "final_label": evaluation.final_label,
                "summary_line": evaluation.summary_line,
                "prefilter_hit_count": evaluation.prefilter_hit_count,
                "structure_score": evaluation.structure_score,
                "ma60_early_signal": evaluation.ma60_early_signal,
                "ma60_deep_below_ma120_ok": evaluation.ma60_deep_below_ma120_ok,
                "ma60_turning_up_ok": evaluation.ma60_turning_up_ok,
                "close_near_ma60_ok": evaluation.close_near_ma60_ok,
                "close_above_ma60_ok": evaluation.close_above_ma60_ok,
                "ma60": inputs.ma60,
                "ma120": inputs.ma120,
                "ma250": inputs.ma250,
                "ma60_below_ma120_min_gap": inputs.ma60_below_ma120_min_gap,
                "ma60_current_gap_to_ma120": inputs.ma60_current_gap_to_ma120,
                "ma60_slope_20d": inputs.ma60_slope_20d,
                "close_to_ma60_gap": inputs.close_to_ma60_gap,
                "breakout_emerged": evaluation.breakout_emerged,
                "breakout_confirmed": evaluation.breakout_confirmed,
                "leader_turning_strong_ok": evaluation.leader_turning_strong_ok,
                "leader_confirmed_ok": evaluation.leader_confirmed_ok,
                "leader_count": inputs.leader_count,
                "leader_group_names": inputs.leader_group_names,
                "leader_group_detail": inputs.leader_group_detail,
                "leader_active_count": inputs.leader_active_count,
                "leader_top1_name": inputs.leader_top1_name,
                "leader_top1_pct_change": inputs.leader_top1_pct_change,
                "leader_top1_above_ma60": inputs.leader_top1_above_ma60,
                "leader_top1_above_ma250": inputs.leader_top1_above_ma250,
                "leader_follow_ok": inputs.leader_follow_ok,
                "leader_5d_rank_pct": inputs.leader_5d_rank_pct,
                "leaders_above_ma60_count": inputs.leaders_above_ma60_count,
                "leaders_above_ma250_count": inputs.leaders_above_ma250_count,
                "leaders_above_ma60_ratio": inputs.leaders_above_ma60_ratio,
                "leaders_above_ma250_ratio": inputs.leaders_above_ma250_ratio,
                "local_activity_ok": inputs.local_activity_ok,
                "has_ma250": inputs.ma250 is not None,
                "has_amount_ma20": inputs.amount_ma20 is not None,
                "has_ret_120d_rank": inputs.ret_120d_rank_pct is not None,
                "industry_amount": crowding["industry_amount"],
                "market_amount": crowding["market_amount"],
                "absorption_rate": crowding["absorption_rate"],
                "absorption_rate_rank_pct": crowding["absorption_rate_rank_pct"],
                "absorption_rate_5d_change": crowding["absorption_rate_5d_change"],
                "crowding_label": crowding["crowding_label"],
                "crowding_note": crowding["crowding_note"],
            }
        )

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["final_label"] = pd.Categorical(df["final_label"], categories=GROUP_ORDER, ordered=True)
    return df.sort_values(
        ["final_label", "prefilter_label", "total_mv_yi"],
        ascending=[True, True, False],
    ).reset_index(drop=True)


def write_summary(df: pd.DataFrame, min_total_mv_yi: float) -> None:
    final_counts = df["final_label"].value_counts(dropna=False).to_dict()
    prefilter_counts = df["prefilter_label"].value_counts(dropna=False).to_dict()
    crowding_counts = df["crowding_label"].value_counts(dropna=False).to_dict()

    lines = [
        "# 申万二级行业完整扫描结果",
        "",
        "- 口径：申万二级行业主候选池",
        f"- 门槛：总市值 >= `{min_total_mv_yi:.0f}亿`",
        f"- 扫描行业数：`{len(df)}`",
        "",
        "## 分流统计",
        "",
    ]

    for label, count in prefilter_counts.items():
        lines.append(f"- `{label}`：`{count}`")

    lines.extend(["", "## 最终标签统计", ""])
    for label in GROUP_ORDER:
        count = int((df["final_label"] == label).sum())
        lines.append(f"- `{label}`：`{count}`")

    for label, count in final_counts.items():
        if label not in GROUP_ORDER:
            lines.append(f"- `{label}`：`{count}`")

    lines.extend(["", "## 拥挤度辅助标签", ""])
    for label, count in crowding_counts.items():
        lines.append(f"- `{label}`：`{count}`")

    lines.extend(["", "## 观察中样例", ""])
    watch_df = df[df["final_label"] == "观察中"].head(15)
    if watch_df.empty:
        lines.append("- （空）")
    else:
        for _, row in watch_df.iterrows():
            leader_pct = "-"
            if pd.notna(row["leader_top1_pct_change"]):
                leader_pct = f"{float(row['leader_top1_pct_change']):.2f}%"
            leader_count = 0 if pd.isna(row["leader_count"]) else int(row["leader_count"])
            active_count = 0 if pd.isna(row["leader_active_count"]) else int(row["leader_active_count"])
            ma60_count = 0 if pd.isna(row["leaders_above_ma60_count"]) else int(row["leaders_above_ma60_count"])
            leader_detail = row.get("leader_group_detail", "")
            lines.append(
                f"- `{row['industry_name']}` `{row['industry_code']}`"
                f" | 一级：`{row['l1_name']}`"
                f" | 龙头：`{row['leader_top1_name'] or '-'}`"
                f" | 龙头涨跌：`{leader_pct}`"
                f" | 龙头群：`{active_count}/{leader_count}活跃，{ma60_count}/{leader_count}站上MA60`"
                f" | 明细：{leader_detail}"
                f" | 拥挤：`{row['crowding_label']}`"
            )

    OUTPUT_SUMMARY_MD.write_text("\n".join(lines), encoding="utf-8")


def write_leaderboard(df: pd.DataFrame, min_total_mv_yi: float) -> None:
    lines = [
        "# 申万二级行业分层榜单",
        "",
        "> 这套策略抓的是“刚要起来”的细分行业，不是“已经很强”的细分行业。",
        "> 长趋势强赛道应优先归入“趋势延续对象”，而不是误判成“启动确认”。",
        "> `观察中` 代表内部预警，不代表已经启动；只有三条核心条件同时闭环，才算严格意义上的“启动确认”。",
        "",
        f"- 数据口径：申万二级行业，总市值门槛 `>= {min_total_mv_yi:.0f}亿`",
        f"- 当前扫描行业数：`{len(df)}`",
        "",
    ]

    for label in GROUP_ORDER:
        count = int((df["final_label"] == label).sum())
        lines.append(f"- `{label}`：`{count}`")

    lines.append("")

    for label in GROUP_ORDER:
        lines.append(f"## {label}")
        lines.append("")
        group = df[df["final_label"] == label].copy()
        if group.empty:
            lines.append("- （空）")
            lines.append("")
            continue
        for _, row in group.iterrows():
            leader_pct = "-"
            if pd.notna(row["leader_top1_pct_change"]):
                leader_pct = f"{float(row['leader_top1_pct_change']):.2f}%"
            absorption_rank = "-"
            if pd.notna(row["absorption_rate_rank_pct"]):
                absorption_rank = f"{float(row['absorption_rate_rank_pct']):.1%}"
            leader_count = 0 if pd.isna(row["leader_count"]) else int(row["leader_count"])
            active_count = 0 if pd.isna(row["leader_active_count"]) else int(row["leader_active_count"])
            ma60_count = 0 if pd.isna(row["leaders_above_ma60_count"]) else int(row["leaders_above_ma60_count"])
            leader_detail = row.get("leader_group_detail", "")
            lines.append(
                f"- `{row['industry_name']}` `{row['industry_code']}`"
                f" | 一级：`{row['l1_name']}`"
                f" | 龙头：`{row['leader_top1_name'] or '-'}`"
                f" | 龙头涨跌：`{leader_pct}`"
                f" | 龙头群：`{active_count}/{leader_count}活跃，{ma60_count}/{leader_count}站上MA60`"
                f" | 明细：{leader_detail}"
                f" | 拥挤：`{row['crowding_label']}`"
                f" | 吸筹率分位：`{absorption_rank}`"
                f" | 摘要：{row['summary_line']}"
            )
        lines.append("")

    OUTPUT_LEADERBOARD_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    df = run_scan(end_date=DEFAULT_END_DATE, min_total_mv_yi=DEFAULT_THRESHOLD_YI)
    if df.empty:
        raise RuntimeError("No L2 industries were scanned.")
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    write_summary(df, min_total_mv_yi=DEFAULT_THRESHOLD_YI)
    write_leaderboard(df, min_total_mv_yi=DEFAULT_THRESHOLD_YI)
    pd.set_option("display.width", 300)
    pd.set_option("display.max_columns", 40)
    print(df.head(30).to_string(index=False))


if __name__ == "__main__":
    main()

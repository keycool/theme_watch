from dataclasses import asdict
import json
from pathlib import Path
from typing import List

import pandas as pd

from build_sw_l2_focus_leaderboard import build_leader_snapshots_l2, load_classify
from build_sw_l2_sample_pool import DEFAULT_THRESHOLD_YI, build_sample_pool
from build_sw_l1_sample_pool import DEFAULT_END_DATE, get_pro
from industry_start_strategy_v1_engine import StrategyInputs, evaluate_strategy
from run_sw_l1_strategy_scan import (
    MASTER_HISTORY_PATH,
    _build_histories,
    _build_strategy_input,
    _compute_ret_120d_ranks,
)


ROOT = Path(__file__).resolve().parent
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
    "观察中",
    "未启动",
]


def _write_generated_input(inputs: StrategyInputs) -> None:
    path = GENERATED_INPUT_DIR / f"{inputs.industry_code}.json"
    path.write_text(json.dumps(asdict(inputs), ensure_ascii=False, indent=2), encoding="utf-8")


def _load_history() -> pd.DataFrame:
    return pd.read_csv(MASTER_HISTORY_PATH, dtype={"ts_code": str, "trade_date": str})


def run_scan(end_date: str, min_total_mv_yi: float) -> pd.DataFrame:
    sample_pool = build_sample_pool(end_date=end_date, threshold_yi=min_total_mv_yi)
    pool = sample_pool[sample_pool["passes_total_mv_gate"]].copy().reset_index(drop=True)
    if pool.empty:
        return pd.DataFrame()

    classify_df = load_classify()
    history_df = _load_history()
    histories = _build_histories(history_df)
    ret_120d_ranks = _compute_ret_120d_ranks(histories)
    pro = get_pro()
    leader_snapshots = build_leader_snapshots_l2(
        pro=pro,
        latest_date=str(pool["latest_date"].dropna().iloc[0]),
        classify_df=classify_df,
        industry_codes=pool["industry_code"].dropna().astype(str).tolist(),
    )

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
            }
        )

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values(
        ["final_label", "prefilter_label", "total_mv_yi"],
        ascending=[True, True, False],
    ).reset_index(drop=True)


def _format_pct(value) -> str:
    if pd.isna(value):
        return "-"
    return f"{float(value):.2f}%"


def write_summary(df: pd.DataFrame, min_total_mv_yi: float) -> None:
    final_counts = df["final_label"].value_counts(dropna=False).to_dict()
    prefilter_counts = df["prefilter_label"].value_counts(dropna=False).to_dict()

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
    for label, count in final_counts.items():
        lines.append(f"- `{label}`：`{count}`")

    lines.extend(["", "## 观察中样例", ""])
    watch_df = df[df["final_label"] == "观察中"].head(15)
    if watch_df.empty:
        lines.append("- （空）")
    else:
        for _, row in watch_df.iterrows():
            lines.append(
                f"- `{row['industry_name']}` `{row['industry_code']}`"
                f" | 一级：`{row['l1_name']}`"
                f" | 龙头：`{row['leader_top1_name'] or '-'}`"
                f" | 龙头涨跌：`{_format_pct(row['leader_top1_pct_change'])}`"
            )

    OUTPUT_SUMMARY_MD.write_text("\n".join(lines), encoding="utf-8")


def write_leaderboard(df: pd.DataFrame, min_total_mv_yi: float) -> None:
    lines = [
        "# 申万二级行业分层榜单",
        "",
        "> 这套策略抓的是“刚要起来”的细分行业，不是“已经很强”的细分行业。",
        "> 因此，长趋势强赛道应优先被归入“趋势延续对象”，而不是误判成“启动确认”。",
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
            lines.append(
                f"- `{row['industry_name']}` `{row['industry_code']}`"
                f" | 一级：`{row['l1_name']}`"
                f" | 龙头：`{row['leader_top1_name'] or '-'}`"
                f" | 龙头涨跌：`{_format_pct(row['leader_top1_pct_change'])}`"
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
    pd.set_option("display.width", 260)
    pd.set_option("display.max_columns", 32)
    print(df.head(30).to_string(index=False))


if __name__ == "__main__":
    main()

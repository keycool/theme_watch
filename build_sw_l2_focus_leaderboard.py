import json
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

import pandas as pd

from industry_start_strategy_v1_engine import StrategyInputs, evaluate_strategy
from strategy_scan_common import build_histories, build_strategy_input, compute_ret_120d_ranks
from sw_data_utils import get_daily_basic, get_daily_market, get_pro, get_members_by_level, get_stock_daily_with_cache


ROOT = Path(__file__).resolve().parent
CLASSIFY_PATH = ROOT / ".cache_scan_v2" / "sw_index_classify.csv"
MASTER_HISTORY_PATH = ROOT / ".cache_scan_v2" / "sw_daily_full_history.csv"
OUTPUT_MD = ROOT / "sw_l2_focus_leaderboard.md"
OUTPUT_CSV = ROOT / "sw_l2_focus_scan.csv"

MIN_LEADER_GROUP_SIZE = 3
MAX_LEADER_GROUP_SIZE = 10
LEADER_GROUP_COVERAGE = 0.60

FOCUS_L1 = {
    "电子": "270000",
    "电力设备": "630000",
    "计算机": "710000",
    "传媒": "720000",
    "通信": "730000",
}


def load_classify() -> pd.DataFrame:
    return pd.read_csv(CLASSIFY_PATH, dtype=str)


def load_history() -> pd.DataFrame:
    return pd.read_csv(MASTER_HISTORY_PATH, dtype={"ts_code": str, "trade_date": str})


def build_focus_l2_pool(classify_df: pd.DataFrame, history_df: pd.DataFrame) -> pd.DataFrame:
    latest_date = str(history_df["trade_date"].max())
    latest_daily = history_df[history_df["trade_date"] == latest_date].copy()
    latest_daily["total_mv"] = pd.to_numeric(latest_daily["total_mv"], errors="coerce")

    frames: List[pd.DataFrame] = []
    for l1_name, parent_code in FOCUS_L1.items():
        l2 = classify_df[
            (classify_df["level"] == "L2") & (classify_df["parent_code"] == parent_code)
        ][["index_code", "industry_name"]].drop_duplicates()
        merged = l2.merge(
            latest_daily[["ts_code", "trade_date", "close", "pct_change", "amount", "total_mv"]],
            left_on="index_code",
            right_on="ts_code",
            how="left",
        )
        merged["l1_name"] = l1_name
        merged["latest_date"] = merged["trade_date"]
        merged["total_mv_yi"] = merged["total_mv"] / 10000.0
        frames.append(
            merged[
                [
                    "l1_name",
                    "index_code",
                    "industry_name",
                    "latest_date",
                    "close",
                    "pct_change",
                    "amount",
                    "total_mv",
                    "total_mv_yi",
                ]
            ]
        )
    return pd.concat(frames, ignore_index=True)


def get_members_by_index_code(pro, index_code: str, classify_df: pd.DataFrame) -> pd.DataFrame:
    row = classify_df[classify_df["index_code"] == index_code]
    if row.empty:
        return pd.DataFrame()
    level = str(row.iloc[0]["level"])
    return get_members_by_level(pro, index_code, level)


def select_leader_group(members: pd.DataFrame) -> pd.DataFrame:
    leaders = members.sort_values("total_mv", ascending=False).reset_index(drop=True).copy()
    leaders["total_mv"] = pd.to_numeric(leaders["total_mv"], errors="coerce")
    leaders = leaders[leaders["total_mv"].notna() & (leaders["total_mv"] > 0)].copy()
    if leaders.empty:
        return leaders

    total_mv = float(leaders["total_mv"].sum())
    leaders["coverage"] = leaders["total_mv"].cumsum() / total_mv if total_mv else 0
    coverage_count = int((leaders["coverage"] < LEADER_GROUP_COVERAGE).sum()) + 1
    target_count = max(MIN_LEADER_GROUP_SIZE, coverage_count)
    target_count = min(MAX_LEADER_GROUP_SIZE, target_count, len(leaders))
    return leaders.head(target_count).copy()


def _format_leader_detail(name: str, pct_change: object) -> str:
    if pct_change is None or pd.isna(pct_change):
        return f"{name} -"
    return f"{name} {float(pct_change):+.2f}%"


def build_leader_snapshots_l2(pro, latest_date: str, classify_df: pd.DataFrame, industry_codes: List[str]) -> dict[str, dict]:
    latest_basic = get_daily_basic(pro, latest_date)
    latest_market = get_daily_market(pro, latest_date)
    latest_basic["total_mv"] = pd.to_numeric(latest_basic["total_mv"], errors="coerce")
    latest_market["pct_chg"] = pd.to_numeric(latest_market["pct_chg"], errors="coerce")

    snapshots: dict[str, dict] = {}
    for code in industry_codes:
        members = get_members_by_index_code(pro, code, classify_df)
        if members.empty:
            continue
        members = members[members["is_new"] == "Y"][["ts_code", "name"]].drop_duplicates()
        leaders = (
            members.merge(latest_basic[["ts_code", "total_mv"]], on="ts_code", how="inner")
        )
        leaders = select_leader_group(leaders)
        if leaders.empty:
            continue

        leader_top1 = leaders.iloc[0]
        market_row = latest_market[latest_market["ts_code"] == leader_top1["ts_code"]]
        top1_pct = None if market_row.empty else float(market_row.iloc[0]["pct_chg"])

        leader_rows: List[dict] = []
        above_ma60 = None
        above_ma250 = None
        follow_ok = None
        leader_5d_rank_pct = None
        for _, leader in leaders.iterrows():
            daily = get_stock_daily_with_cache(
                pro,
                ts_code=str(leader["ts_code"]),
                start_date="20240101",
                end_date=latest_date,
            )
            market_row = latest_market[latest_market["ts_code"] == leader["ts_code"]]
            pct_change = None if market_row.empty else float(market_row.iloc[0]["pct_chg"])
            row_above_ma60 = None
            row_above_ma250 = None
            row_follow_ok = None
            row_ret_5d = None
            if not daily.empty:
                daily["ma60"] = daily["close"].rolling(60).mean()
                daily["ma250"] = daily["close"].rolling(250).mean()
                last = daily.iloc[-1]
                if pct_change is None and "pct_chg" in daily.columns and pd.notna(last.get("pct_chg")):
                    pct_change = float(last["pct_chg"])
                if pct_change is None and "pct_change" in daily.columns and pd.notna(last.get("pct_change")):
                    pct_change = float(last["pct_change"])
                if pd.notna(last["ma60"]):
                    row_above_ma60 = bool(last["close"] >= last["ma60"])
                if pd.notna(last["ma250"]):
                    row_above_ma250 = bool(last["close"] >= last["ma250"])
                if len(daily) >= 2:
                    row_follow_ok = bool(daily.iloc[-1]["close"] > daily.iloc[-2]["close"])
                if len(daily) >= 6:
                    row_ret_5d = float(daily.iloc[-1]["close"] / daily.iloc[-6]["close"] - 1)

            row_active = bool(
                (pct_change is not None and pct_change >= 5)
                or (row_ret_5d is not None and row_ret_5d >= 0.05)
            )
            leader_rows.append(
                {
                    "name": str(leader["name"]),
                    "pct_change": pct_change,
                    "above_ma60": row_above_ma60,
                    "above_ma250": row_above_ma250,
                    "follow_ok": row_follow_ok,
                    "ret_5d": row_ret_5d,
                    "active": row_active,
                }
            )

            if str(leader["ts_code"]) == str(leader_top1["ts_code"]):
                top1_pct = pct_change
                above_ma60 = row_above_ma60
                above_ma250 = row_above_ma250
                follow_ok = row_follow_ok
                leader_5d_rank_pct = row_ret_5d

        leader_count = len(leader_rows)
        active_count = sum(1 for row in leader_rows if row["active"])
        above_ma60_count = sum(1 for row in leader_rows if row["above_ma60"] is True)
        above_ma250_count = sum(1 for row in leader_rows if row["above_ma250"] is True)
        follow_count = sum(1 for row in leader_rows if row["follow_ok"] is True)
        leader_group_names = "、".join(row["name"] for row in leader_rows)
        leader_group_detail = "、".join(
            _format_leader_detail(row["name"], row["pct_change"]) for row in leader_rows
        )

        snapshots[code] = {
            "leader_count": int(leader_count),
            "leader_group_names": leader_group_names,
            "leader_group_detail": leader_group_detail,
            "leader_active_count": int(active_count),
            "leader_top1_name": str(leader_top1["name"]),
            "leader_top1_pct_change": top1_pct,
            "leader_top1_above_ma60": above_ma60,
            "leader_top1_above_ma250": above_ma250,
            "leader_follow_ok": follow_ok,
            "leader_5d_rank_pct": leader_5d_rank_pct,
            "leaders_above_ma60_count": int(above_ma60_count),
            "leaders_above_ma250_count": int(above_ma250_count),
            "leaders_above_ma60_ratio": above_ma60_count / leader_count if leader_count else None,
            "leaders_above_ma250_ratio": above_ma250_count / leader_count if leader_count else None,
            "leaders_follow_count": int(follow_count),
            "leaders_follow_ratio": follow_count / leader_count if leader_count else None,
        }
    return snapshots


def run_focus_scan() -> pd.DataFrame:
    classify_df = load_classify()
    history_df = load_history()
    histories = build_histories(history_df)
    ranks = compute_ret_120d_ranks(histories)
    pool = build_focus_l2_pool(classify_df, history_df)

    pro = get_pro()
    leader_snapshots = build_leader_snapshots_l2(
        pro,
        latest_date=str(pool["latest_date"].dropna().iloc[0]),
        classify_df=classify_df,
        industry_codes=pool["index_code"].dropna().astype(str).tolist(),
    )

    rows: List[dict] = []
    for _, row in pool.iterrows():
        code = str(row["index_code"])
        history = histories.get(code)
        if history is None or history.empty:
            continue
        inputs = build_strategy_input(row.rename({"index_code": "industry_code"}), history, ranks.get(code), leader_snapshots.get(code))
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
                "leader_count": inputs.leader_count,
                "leader_group_names": inputs.leader_group_names,
                "leader_group_detail": inputs.leader_group_detail,
                "leader_active_count": inputs.leader_active_count,
                "leader_top1_name": inputs.leader_top1_name,
                "leader_top1_pct_change": inputs.leader_top1_pct_change,
                "leader_top1_above_ma60": inputs.leader_top1_above_ma60,
                "leader_top1_above_ma250": inputs.leader_top1_above_ma250,
                "leaders_above_ma60_count": inputs.leaders_above_ma60_count,
                "leaders_above_ma250_count": inputs.leaders_above_ma250_count,
                "leaders_above_ma60_ratio": inputs.leaders_above_ma60_ratio,
                "leaders_above_ma250_ratio": inputs.leaders_above_ma250_ratio,
            }
        )
    df = pd.DataFrame(rows).sort_values(
        ["l1_name", "final_label", "total_mv_yi"],
        ascending=[True, True, False],
    )
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    return df


def build_markdown(df: pd.DataFrame) -> str:
    alias_lines = [
        "# 重点一级行业下钻二级行业榜单",
        "",
        "- 这是在一级行业主系统之外的二级行业子榜单。",
        "- 用途是把一级行业里你更关心的细分赛道拆出来看。",
        "- 例如：`电子 -> 半导体`，`电力设备 -> 光伏设备`，`TMT -> 计算机/通信/传媒`。",
        "",
    ]
    for l1_name in FOCUS_L1:
        group = df[df["l1_name"] == l1_name].copy()
        alias_lines.append(f"## {l1_name}")
        alias_lines.append("")
        if group.empty:
            alias_lines.append("- （空）")
            alias_lines.append("")
            continue
        for _, row in group.iterrows():
            leader = row["leader_top1_name"] if pd.notna(row["leader_top1_name"]) else "-"
            pct = "-" if pd.isna(row["leader_top1_pct_change"]) else f"{float(row['leader_top1_pct_change']):.2f}%"
            leader_count = 0 if pd.isna(row["leader_count"]) else int(row["leader_count"])
            active_count = 0 if pd.isna(row["leader_active_count"]) else int(row["leader_active_count"])
            ma60_count = 0 if pd.isna(row["leaders_above_ma60_count"]) else int(row["leaders_above_ma60_count"])
            leader_detail = row.get("leader_group_detail", "")
            alias_lines.append(
                f"- `{row['industry_name']}` `{row['industry_code']}`"
                f" | 标签：`{row['final_label']}`"
                f" | 龙头：`{leader}`"
                f" | 龙头涨跌：`{pct}`"
                f" | 龙头群：`{active_count}/{leader_count}活跃，{ma60_count}/{leader_count}站上MA60`"
                f" | 明细：{leader_detail}"
            )
        alias_lines.append("")
    return "\n".join(alias_lines)


def main() -> None:
    df = run_focus_scan()
    OUTPUT_MD.write_text(build_markdown(df), encoding="utf-8")
    print(f"Wrote {OUTPUT_MD}")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()

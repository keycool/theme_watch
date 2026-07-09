import argparse
from pathlib import Path

import pandas as pd

from sw_data_utils import DEFAULT_END_DATE, YI_TO_TUSHARE_MV, get_pro, get_sw_daily


ROOT = Path(__file__).resolve().parent
CLASSIFY_PATH = ROOT / ".cache_scan_v2" / "sw_index_classify.csv"
MASTER_HISTORY_PATH = ROOT / ".cache_scan_v2" / "sw_daily_full_history.csv"
OUTPUT_CSV = ROOT / "sw_l2_sample_pool.csv"
OUTPUT_MD = ROOT / "sw_l2_sample_pool_summary.md"
DEFAULT_THRESHOLD_YI = 2000.0


def load_classify() -> pd.DataFrame:
    return pd.read_csv(CLASSIFY_PATH, dtype=str)


def load_sw_daily_snapshot(pro, end_date: str) -> pd.DataFrame:
    if MASTER_HISTORY_PATH.exists():
        df = pd.read_csv(MASTER_HISTORY_PATH, dtype={"ts_code": str, "trade_date": str})
        df = df[df["trade_date"].astype(str) <= str(end_date)].copy()
        if not df.empty:
            return df
    return get_sw_daily(pro, start_date="20250506", end_date=end_date)


def build_sample_pool(end_date: str, threshold_yi: float) -> pd.DataFrame:
    pro = get_pro()
    classify_df = load_classify()
    industries = classify_df[classify_df["level"] == "L2"][
        ["index_code", "industry_name", "parent_code", "industry_code"]
    ].drop_duplicates().rename(
        columns={
            "index_code": "l2_index_code",
            "industry_name": "l2_name",
            "industry_code": "l2_industry_code",
        }
    )

    sw_daily = load_sw_daily_snapshot(pro, end_date=end_date)
    if sw_daily.empty:
        raise RuntimeError("sw_daily returned no rows, cannot build sample pool.")

    latest_date = str(sw_daily["trade_date"].max())
    latest_daily = sw_daily[sw_daily["trade_date"] == latest_date].copy()

    l1_lookup = classify_df[classify_df["level"] == "L1"][
        ["industry_code", "industry_name"]
    ].rename(columns={"industry_name": "l1_name", "industry_code": "l1_industry_code"})

    merged = industries.merge(
        latest_daily[
            ["ts_code", "trade_date", "name", "close", "pct_change", "amount", "float_mv", "total_mv"]
        ],
        left_on="l2_index_code",
        right_on="ts_code",
        how="left",
    ).merge(
        l1_lookup,
        left_on="parent_code",
        right_on="l1_industry_code",
        how="left",
        suffixes=("", "_l1"),
    )

    threshold_mv = threshold_yi * YI_TO_TUSHARE_MV
    merged["total_mv_yi"] = merged["total_mv"] / YI_TO_TUSHARE_MV
    merged["float_mv_yi"] = merged["float_mv"] / YI_TO_TUSHARE_MV
    merged["passes_total_mv_gate"] = merged["total_mv"] >= threshold_mv

    merged = merged.rename(
        columns={
            "l2_index_code": "industry_code",
            "l2_name": "industry_name",
            "trade_date": "latest_date",
            "name": "sw_name",
        }
    )

    columns = [
        "industry_code",
        "industry_name",
        "l1_name",
        "latest_date",
        "close",
        "pct_change",
        "amount",
        "float_mv",
        "float_mv_yi",
        "total_mv",
        "total_mv_yi",
        "passes_total_mv_gate",
    ]
    merged = merged[columns].sort_values(
        ["passes_total_mv_gate", "total_mv", "industry_code"],
        ascending=[False, False, True],
    )
    return merged.reset_index(drop=True)


def write_summary(df: pd.DataFrame, threshold_yi: float) -> None:
    in_pool = df[df["passes_total_mv_gate"]].copy()
    out_pool = df[~df["passes_total_mv_gate"]].copy()
    latest_date = df["latest_date"].dropna().astype(str).max() if not df.empty else "N/A"

    lines = [
        "# 申万二级行业主候选池",
        "",
        f"- 最新交易日：`{latest_date}`",
        f"- 二级行业总数：`{len(df)}`",
        f"- 入池门槛：`总市值 >= {threshold_yi:.0f}亿`",
        f"- 入池行业数：`{len(in_pool)}`",
        f"- 池外行业数：`{len(out_pool)}`",
        "",
        "## 一级行业分布",
        "",
    ]

    if in_pool.empty:
        lines.append("- 当前没有二级行业满足门槛。")
    else:
        for l1_name, group in in_pool.groupby("l1_name"):
            lines.append(f"- `{l1_name}`：`{len(group)}`")

    lines.extend(["", "## 入池样例（前 30）", ""])
    for _, row in in_pool.head(30).iterrows():
        lines.append(
            f"- `{row['industry_name']}` `{row['industry_code']}` | 一级：`{row['l1_name']}` | 总市值：`{row['total_mv_yi']:.0f}亿`"
        )

    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="构建申万二级行业主候选池")
    parser.add_argument("--end-date", default=DEFAULT_END_DATE, help="行业日线截止日期，格式 YYYYMMDD")
    parser.add_argument(
        "--min-total-mv-yi",
        type=float,
        default=DEFAULT_THRESHOLD_YI,
        help="主候选池最小总市值门槛，单位：亿元",
    )
    args = parser.parse_args()

    df = build_sample_pool(end_date=args.end_date, threshold_yi=args.min_total_mv_yi)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    write_summary(df, threshold_yi=args.min_total_mv_yi)

    in_pool = df[df["passes_total_mv_gate"]].copy()
    print(f"latest_date={df['latest_date'].dropna().astype(str).max()}")
    print(f"threshold_yi={args.min_total_mv_yi:.0f}")
    print(f"industry_count={len(df)}")
    print(f"in_pool_count={len(in_pool)}")
    if not in_pool.empty:
        print(in_pool[["industry_code", "industry_name", "l1_name", "total_mv_yi"]].head(30).to_string(index=False))


if __name__ == "__main__":
    main()

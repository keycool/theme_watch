import argparse
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
OUTPUT_CSV = ROOT / "sw_l1_sample_pool.csv"
OUTPUT_MD = ROOT / "sw_l1_sample_pool_summary.md"
DEFAULT_END_DATE = "20260630"
DEFAULT_THRESHOLD_YI = 5000.0
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
        if "频率超限" in str(exc):
            raise RuntimeError(
                f"{name} is rate-limited and has no local cache yet. Retry after the limit window. Original error: {exc}"
            )
        raise


def get_sw_l1_industries(pro) -> pd.DataFrame:
    df = fetch_with_cache(
        "sw_index_classify",
        lambda: pro.index_classify(src="SW2021"),
        dtype=str,
    )
    columns = ["index_code", "industry_name"]
    return df[df["level"] == "L1"][columns].drop_duplicates().copy()


def get_sw_daily(pro, start_date: str, end_date: str) -> pd.DataFrame:
    df = fetch_with_cache(
        f"sw_daily_{start_date}_{end_date}",
        lambda: pro.sw_daily(start_date=start_date, end_date=end_date),
    )
    for col in ["ts_code", "trade_date", "name"]:
        if col in df.columns:
            df[col] = df[col].astype(str)
    numeric_cols = ["close", "pct_change", "float_mv", "total_mv", "amount"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def build_sample_pool(end_date: str, threshold_yi: float) -> pd.DataFrame:
    pro = get_pro()
    industries = get_sw_l1_industries(pro)
    start_date = "20250506"
    sw_daily = get_sw_daily(pro, start_date=start_date, end_date=end_date)

    if sw_daily.empty:
        raise RuntimeError("sw_daily returned no rows, cannot build sample pool.")

    latest_date = str(sw_daily["trade_date"].max())
    latest_daily = sw_daily[sw_daily["trade_date"] == latest_date].copy()

    merged = industries.merge(
        latest_daily[
            ["ts_code", "trade_date", "name", "close", "pct_change", "amount", "float_mv", "total_mv"]
        ],
        left_on="index_code",
        right_on="ts_code",
        how="left",
    )

    threshold_mv = threshold_yi * YI_TO_TUSHARE_MV
    merged["total_mv_yi"] = merged["total_mv"] / YI_TO_TUSHARE_MV
    merged["float_mv_yi"] = merged["float_mv"] / YI_TO_TUSHARE_MV
    merged["passes_total_mv_gate"] = merged["total_mv"] >= threshold_mv

    merged = merged.rename(
        columns={
            "index_code": "industry_code",
            "industry_name": "industry_name",
            "trade_date": "latest_date",
            "name": "sw_name",
        }
    )

    merged["sample_pool"] = merged["passes_total_mv_gate"].map(
        {True: "主扫描池", False: "池外"}
    )

    columns = [
        "industry_code",
        "industry_name",
        "latest_date",
        "close",
        "pct_change",
        "amount",
        "float_mv",
        "float_mv_yi",
        "total_mv",
        "total_mv_yi",
        "passes_total_mv_gate",
        "sample_pool",
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
        "# 申万一级行业主样本池",
        "",
        f"- 最新交易日：`{latest_date}`",
        f"- 总行业数：`{len(df)}`",
        f"- 入池门槛：`总市值 >= {threshold_yi:.0f}亿`",
        f"- 入池行业数：`{len(in_pool)}`",
        f"- 池外行业数：`{len(out_pool)}`",
        "",
        "## 入池行业",
        "",
    ]

    if in_pool.empty:
        lines.append("- 当前没有行业满足门槛。")
    else:
        for _, row in in_pool.iterrows():
            lines.append(
                f"- `{row['industry_name']}` `{row['industry_code']}`：总市值 `{row['total_mv_yi']:.0f}亿`"
            )

    lines.extend(["", "## 说明", "", "- 当前主样本池只按申万一级行业和总市值门槛筛选。", "- 这一步还没有进入启动/趋势规则判定。"])
    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="构建申万一级行业主样本池")
    parser.add_argument("--end-date", default=DEFAULT_END_DATE, help="行业日线截止日期，格式 YYYYMMDD")
    parser.add_argument(
        "--min-total-mv-yi",
        type=float,
        default=DEFAULT_THRESHOLD_YI,
        help="主样本池最小总市值门槛，单位：亿元",
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
        print(in_pool[["industry_code", "industry_name", "total_mv_yi"]].head(20).to_string(index=False))


if __name__ == "__main__":
    main()

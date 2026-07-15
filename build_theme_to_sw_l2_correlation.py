from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from sw_data_utils import get_pro


ROOT = Path(__file__).resolve().parent
HISTORY_CSV = ROOT / ".cache_scan_v2" / "sw_daily_full_history.csv"
CLASSIFY_CSV = ROOT / ".cache_scan_v2" / "sw_index_classify.csv"
SCAN_CSV = ROOT / "sw_l2_strategy_scan.csv"
CACHE_DIR = ROOT / ".cache_scan_v2"


def _return_series(df: pd.DataFrame, close_col: str, pct_col: str | None = None) -> pd.Series:
    if pct_col and pct_col in df.columns:
        pct = pd.to_numeric(df[pct_col], errors="coerce")
        if pct.notna().sum() > 0:
            return pct / 100.0
    return pd.to_numeric(df[close_col], errors="coerce").pct_change()


def _load_theme_daily(
    ts_code: str,
    source: str,
    start_date: str,
    end_date: str,
    force_refresh: bool = False,
) -> pd.DataFrame:
    cache_key = ts_code.replace(".", "_")
    cache_path = CACHE_DIR / f"{source}_daily_{cache_key}_{start_date}_{end_date}.csv"
    if cache_path.exists() and not force_refresh:
        return pd.read_csv(cache_path, dtype={"ts_code": str, "trade_date": str})

    pro = get_pro()
    if source == "fund":
        df = pro.fund_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
    elif source == "index":
        df = pro.index_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
    else:
        raise ValueError(f"Unsupported source: {source}")

    df.to_csv(cache_path, index=False, encoding="utf-8-sig")
    return df


def build_correlation(
    ts_code: str,
    source: str,
    start_date: str,
    end_date: str,
    output: Path,
    force_refresh: bool = False,
) -> pd.DataFrame:
    theme = _load_theme_daily(
        ts_code,
        source,
        start_date,
        end_date,
        force_refresh=force_refresh,
    ).sort_values("trade_date").copy()
    if theme.empty:
        raise RuntimeError(f"{source}_daily returned no rows for {ts_code}.")
    theme["theme_ret"] = _return_series(theme, close_col="close", pct_col="pct_chg")

    classify = pd.read_csv(CLASSIFY_CSV, dtype=str)
    l2_codes = set(classify[classify["level"] == "L2"]["index_code"].astype(str))

    sw = pd.read_csv(HISTORY_CSV, dtype={"ts_code": str, "trade_date": str})
    sw = sw[sw["ts_code"].isin(l2_codes)].sort_values(["ts_code", "trade_date"]).copy()
    sw["close"] = pd.to_numeric(sw["close"], errors="coerce")
    if "pct_change" in sw.columns:
        sw["sw_ret"] = pd.to_numeric(sw["pct_change"], errors="coerce") / 100.0
    else:
        sw["sw_ret"] = sw.groupby("ts_code")["close"].pct_change()

    scan = pd.read_csv(SCAN_CSV)
    scan_map = scan.set_index("industry_code").to_dict("index")

    rows: list[dict] = []
    for code, group in sw.groupby("ts_code"):
        merged = pd.merge(
            theme[["trade_date", "theme_ret"]],
            group[["trade_date", "sw_ret"]],
            on="trade_date",
            how="inner",
        ).dropna()
        if len(merged) < 120:
            continue
        latest_common_date = str(merged["trade_date"].max())
        first_common_date = str(merged["trade_date"].min())

        info = scan_map.get(code, {})
        fallback_name = ""
        if "name" in group.columns and group["name"].notna().any():
            fallback_name = str(group["name"].dropna().iloc[-1])

        rows.append(
            {
                "theme_code": ts_code,
                "sw_code": code,
                "sw_name": info.get("industry_name", fallback_name),
                "l1_name": info.get("l1_name", ""),
                "corr_daily_ret": float(merged["theme_ret"].corr(merged["sw_ret"])),
                "common_days": len(merged),
                "first_common_date": first_common_date,
                "latest_common_date": latest_common_date,
                "final_label": info.get("final_label", ""),
                "crowding_label": info.get("crowding_label", ""),
                "total_mv_yi": info.get("total_mv_yi", None),
                "leader_top1_name": info.get("leader_top1_name", ""),
            }
        )

    result = pd.DataFrame(rows).sort_values("corr_daily_ret", ascending=False).reset_index(drop=True)
    result.to_csv(output, index=False, encoding="utf-8-sig")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ts-code", required=True)
    parser.add_argument("--source", choices=["fund", "index"], default="fund")
    parser.add_argument("--start-date", default="20240101")
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--force-refresh", action="store_true")
    args = parser.parse_args()

    result = build_correlation(
        ts_code=args.ts_code,
        source=args.source,
        start_date=args.start_date,
        end_date=args.end_date,
        output=Path(args.output),
        force_refresh=args.force_refresh,
    )
    print(result.head(15).to_string(index=False))


if __name__ == "__main__":
    main()

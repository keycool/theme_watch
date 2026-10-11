"""拉取急跌形态研究所需的 ETF 日线（前复权），落盘为 CSV。

数据源：akshare fund_etf_hist_em（东财）。
范围：2026-01-01 ~ 2026-09-22（覆盖客户甲给的全部区间 + 后续 40+ 交易日用于观察修复）。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import akshare as ak
import pandas as pd

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
RAW.mkdir(exist_ok=True)

START = "20260101"
END = "20260922"

# 客户甲点名的 10 只 + 宽基基准
TARGETS = {
    "159915": "创业板ETF",
    "588050": "科创50ETF",
    "563300": "中证2000ETF",
    "515180": "红利ETF",
    "512890": "红利低波ETF",
    "512010": "医药ETF",
    "512170": "医疗ETF",
    "159992": "创新药ETF",
    "515220": "煤炭ETF",
    "159611": "电力ETF",
    # 基准/参照
    "510300": "沪深300ETF",
    "512100": "中证1000ETF",
    "588000": "科创50ETF华夏",
    "159949": "创业板50",
    "510500": "中证500ETF",
    "512480": "半导体ETF",
    "515790": "光伏ETF",
    "512400": "有色金属ETF",
    "512800": "银行ETF",
    "512000": "券商ETF",
    "512690": "酒ETF",
    "515030": "新能车ETF",
    "516160": "新能源ETF",
    "159865": "养殖ETF",
    "512660": "军工ETF",
    "515880": "通信ETF",
    "512720": "计算机ETF",
    "159851": "金融科技ETF",
    "516010": "游戏ETF",
    "159766": "旅游ETF",
    "516110": "汽车ETF",
    "512200": "房地产ETF",
    "516910": "乳业ETF",
    "159928": "消费ETF",
    "515650": "消费50ETF",
    "512170_x": "占位勿用",
}


def fetch_one(code: str) -> pd.DataFrame | None:
    try:
        df = ak.fund_etf_hist_em(
            symbol=code, period="daily", start_date=START, end_date=END, adjust="qfq"
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {code}: {type(exc).__name__}: {exc}")
        return None
    if df is None or df.empty:
        print(f"[EMPTY] {code}")
        return None
    df = df.rename(
        columns={
            "日期": "date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "amount",
            "涨跌幅": "pct",
        }
    )
    keep = ["date", "open", "high", "low", "close", "volume", "amount", "pct"]
    df = df[[c for c in keep if c in df.columns]].copy()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    print(f"[OK] {code} rows={len(df)} {df['date'].iloc[0]}~{df['date'].iloc[-1]}")
    return df


def main() -> None:
    only = sys.argv[1:] if len(sys.argv) > 1 else None
    codes = list(TARGETS)
    if only:
        codes = [c for c in codes if c in only]
    for code in codes:
        name = TARGETS[code]
        if name.endswith("占位勿用"):
            continue
        out = RAW / f"{code}.csv"
        if out.exists() and out.stat().st_size > 200:
            print(f"[SKIP] {code} {name} 已存在")
            continue
        df = fetch_one(code)
        if df is not None:
            df.to_csv(out, index=False, encoding="utf-8-sig")
        time.sleep(0.4)


if __name__ == "__main__":
    main()

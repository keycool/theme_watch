"""按 etf_universe.csv 批量拉日线，过滤货币/债券类。"""
from __future__ import annotations

import time
from pathlib import Path

import akshare as ak
import pandas as pd

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
RAW.mkdir(exist_ok=True)
START = "20260101"
END = "20260922"


def main() -> None:
    uni = pd.read_csv(ROOT / "etf_universe.csv", dtype={"代码": str})
    # 过滤货币/债券类：511/159001/511990 等短融货币，以及名称含 债/货币/添益/日利
    bad_kw = ("债", "货币", "添益", "日利", "短融", "现金", "理财")
    targets = []
    for _, r in uni.iterrows():
        code = str(r["代码"]).zfill(6)
        name = str(r["名称"])
        if code.startswith("511"):
            continue
        if any(k in name for k in bad_kw):
            continue
        targets.append((code, name))
    print(f"待拉 {len(targets)} 只（已过滤货币/债券）")

    ok = fail = skip = 0
    for i, (code, name) in enumerate(targets, 1):
        out = RAW / f"{code}.csv"
        if out.exists() and out.stat().st_size > 200:
            skip += 1
            continue
        try:
            df = ak.fund_etf_hist_em(
                symbol=code, period="daily", start_date=START, end_date=END, adjust="qfq"
            )
        except Exception as exc:  # noqa: BLE001
            fail += 1
            print(f"[FAIL {i}] {code} {name}: {type(exc).__name__}")
            continue
        if df is None or df.empty:
            fail += 1
            print(f"[EMPTY {i}] {code} {name}")
            continue
        df = df.rename(
            columns={
                "日期": "date", "开盘": "open", "收盘": "close", "最高": "high",
                "最低": "low", "成交量": "volume", "成交额": "amount", "涨跌幅": "pct",
            }
        )
        keep = [c for c in ["date", "open", "high", "low", "close", "volume", "amount", "pct"] if c in df.columns]
        df = df[keep].copy()
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df.to_csv(out, index=False, encoding="utf-8-sig")
        ok += 1
        if ok % 20 == 0:
            print(f"... 进度 {i}/{len(targets)} ok={ok} fail={fail}")
        time.sleep(0.3)

    print(f"完成 ok={ok} fail={fail} skip={skip}")


if __name__ == "__main__":
    main()

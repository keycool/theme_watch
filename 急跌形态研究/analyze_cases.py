"""对客户甲点名的急跌案例做形态刻画。

只描述**急跌期间**的事实；后续修复单独列出仅供分组参考，不作为预测依据。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"

# 客户甲给的区间（起=观察起点，止=他认定的急跌终点/低点区）
CASES = [
    ("159915", "创业板ETF", "2026-07-01", "2026-07-30", "回升"),
    ("588050", "科创50ETF", "2026-07-01", "2026-08-03", "回升"),
    ("563300", "中证2000ETF", "2026-07-02", "2026-07-20", "回升"),
    ("515180", "红利ETF", "2026-06-15", "2026-06-30", "回升"),
    ("512890", "红利低波ETF", "2026-06-15", "2026-06-30", "回升"),
    ("512010", "医药ETF", "2026-05-13", "2026-06-09", "回升"),
    ("512170", "医疗ETF", "2026-05-13", "2026-06-09", "回升"),
    ("159992", "创新药ETF", "2026-05-13", "2026-06-09", "回升"),
    ("515220", "煤炭ETF", "2026-06-05", "2026-06-30", "回升"),
    ("159611", "电力ETF", "2026-06-04", "2026-07-09", "未回升"),
]


def load(code: str) -> pd.DataFrame:
    df = pd.read_csv(RAW / f"{code}.csv")
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df["ret"] = df["close"].pct_change() * 100
    for n in (20, 60, 250):
        df[f"ma{n}"] = df["close"].rolling(n).mean()
    df["vol20"] = df["volume"].rolling(20).mean()
    return df


def describe(code: str, name: str, start: str, end: str, group: str) -> dict:
    df = load(code)
    bench = load("510300").set_index("date")["close"]

    s = pd.Timestamp(start)
    e = pd.Timestamp(end)
    # 区间前的基准点：区间起点前一交易日收盘
    pre = df[df["date"] < s]
    pre_close = float(pre["close"].iloc[-1]) if len(pre) else float("nan")
    pre_date = pre["date"].iloc[-1] if len(pre) else None

    seg = df[(df["date"] >= s) & (df["date"] <= e)].copy()
    if seg.empty:
        return {"code": code, "name": name, "error": "区间无数据"}

    end_close = float(seg["close"].iloc[-1])
    seg_high = float(seg["high"].max())
    seg_low = float(seg["low"].min())
    low_date = seg.loc[seg["low"].idxmin(), "date"]
    high_date = seg.loc[seg["high"].idxmax(), "date"]

    drop = (end_close / pre_close - 1) * 100
    mdd = (seg_low / seg_high - 1) * 100

    rets = seg["ret"].dropna()
    days = len(seg)
    worst = float(rets.min()) if len(rets) else float("nan")
    big_down = int((rets <= -2).sum())
    big_down_3 = int((rets <= -3).sum())
    up_days = int((rets > 0).sum())

    # 最大连续下跌（按收盘价）
    streak = 0
    max_streak = 0
    for r in rets:
        if r < 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0

    # 量能：区间日均量 / 区间前 20 日均量
    base_vol = float(pre["volume"].tail(20).mean()) if len(pre) else float("nan")
    vol_ratio = float(seg["volume"].mean()) / base_vol if base_vol else float("nan")

    # 波动放大：区间日收益标准差 / 区间前 20 日标准差
    pre_ret_std = float(pre["ret"].tail(20).std()) if len(pre) else float("nan")
    vola_ratio = float(rets.std()) / pre_ret_std if pre_ret_std else float("nan")

    # 相对沪深300 超额
    b0 = bench.reindex([pre_date], method="ffill").iloc[0] if pre_date is not None else np.nan
    b1 = bench.reindex([seg["date"].iloc[-1]], method="ffill").iloc[0]
    bench_ret = (b1 / b0 - 1) * 100 if b0 == b0 else float("nan")
    excess = drop - bench_ret if bench_ret == bench_ret else float("nan")

    # 均线位置：终点相对 MA20/MA60
    last = seg.iloc[-1]
    ma20_gap = (last["close"] / last["ma20"] - 1) * 100 if last["ma20"] == last["ma20"] else float("nan")
    ma60_gap = (last["close"] / last["ma60"] - 1) * 100 if last["ma60"] == last["ma60"] else float("nan")

    # 后续修复（仅供分组校验，不作预测）
    after = df[df["date"] > e]
    rec20 = float("nan")
    rec_max = float("nan")
    rec_max_days = float("nan")
    if len(after):
        a = after["close"].values
        rec20 = (a[min(19, len(a) - 1)] / end_close - 1) * 100
        rec_max = (a.max() / end_close - 1) * 100
        rec_max_days = int(np.argmax(a)) + 1

    return {
        "code": code,
        "name": name,
        "group": group,
        "起": start,
        "止": end,
        "起始价": round(pre_close, 3),
        "终点价": round(end_close, 3),
        "区间跌%": round(drop, 2),
        "最大回撤%": round(mdd, 2),
        "低点日": str(low_date.date()),
        "高点日": str(high_date.date()),
        "天数": days,
        "日均跌%": round(drop / days, 2),
        "最大单日跌%": round(worst, 2),
        "跌>2%天数": big_down,
        "跌>3%天数": big_down_3,
        "上涨天数": up_days,
        "最大连跌": max_streak,
        "量能比": round(vol_ratio, 2),
        "波动放大": round(vola_ratio, 2),
        "同期300%": round(bench_ret, 2),
        "超额%": round(excess, 2),
        "离MA20%": round(ma20_gap, 2),
        "离MA60%": round(ma60_gap, 2),
        "后20日%": round(rec20, 2),
        "后最大涨%": round(rec_max, 2),
        "见顶天数": rec_max_days,
    }


def main() -> None:
    rows = [describe(*c) for c in CASES]
    df = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 50)

    cols1 = ["name", "code", "group", "起", "止", "区间跌%", "最大回撤%", "天数", "日均跌%", "最大单日跌%"]
    print("=== 一、跌幅与节奏 ===")
    print(df[cols1].to_string(index=False))

    cols2 = ["name", "跌>2%天数", "跌>3%天数", "上涨天数", "最大连跌", "量能比", "波动放大"]
    print("\n=== 二、跌法（急的程度 / 连续性 / 量能） ===")
    print(df[cols2].to_string(index=False))

    cols3 = ["name", "同期300%", "超额%", "离MA20%", "离MA60%", "低点日"]
    print("\n=== 三、相对市场与均线位置 ===")
    print(df[cols3].to_string(index=False))

    cols4 = ["name", "group", "区间跌%", "后20日%", "后最大涨%", "见顶天数", "终点价", "低点日"]
    print("\n=== 四、后续修复（仅供校验分组，不作预测依据） ===")
    print(df[cols4].to_string(index=False))

    df.to_csv(ROOT / "case_features.csv", index=False, encoding="utf-8-sig")
    print(f"\n已写入 {ROOT / 'case_features.csv'}")


if __name__ == "__main__":
    main()

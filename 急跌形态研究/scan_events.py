"""全样本急跌事件扫描 + 修复统计。

设计要点
--------
1. 事件 = 「急跌」，按几何事实定义，**不含任何买卖含义**：
   从过去 20 个交易日内的最高收盘，回撤 >= DEPTH_THRESHOLD，且该回撤
   在 <= WINDOW 个交易日内完成。事件终点 = 回撤低点日。
2. 同一标的的重叠事件合并（保留区间最低点），避免重复计数导致伪样本。
3. 只保留「低点之后还有 >= HOLD_DAYS 个交易日」的事件，否则无法观测修复。
4. ⚠️ 统计口径警告：事件之间高度重叠（同一时间全市场一起跌），
   有效独立样本远少于事件数。本报告只做描述与分层比较，不做显著性声称。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"

DEPTH_THRESHOLD = -10.0   # 回撤阈值（%）
WINDOW = 20               # 回撤须在多少个交易日内完成
HOLD_DAYS = 20            # 观测修复的天数
MIN_BARS = 60             # 标的最少历史长度


def load(code: str) -> pd.DataFrame | None:
    p = RAW / f"{code}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    if len(df) < MIN_BARS:
        return None
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df["ret"] = df["close"].pct_change() * 100
    for n in (20, 60):
        df[f"ma{n}"] = df["close"].rolling(n).mean()
    return df


def find_events(df: pd.DataFrame, code: str, name: str) -> list[dict]:
    """找回撤事件：滚动窗口内 高点->低点 的回撤 >= 阈值。"""
    n = len(df)
    close = df["close"].values
    events: list[dict] = []
    i = WINDOW
    while i < n:
        # 窗口 [i-WINDOW, i] 内的最高点位置
        w_lo = i - WINDOW
        seg = close[w_lo : i + 1]
        hi_rel = int(np.argmax(seg))
        hi_idx = w_lo + hi_rel
        hi = close[hi_idx]
        lo_idx = i
        lo = close[i]
        dd = (lo / hi - 1) * 100
        if dd <= DEPTH_THRESHOLD and hi_idx < lo_idx:
            events.append({"peak_idx": hi_idx, "low_idx": lo_idx, "depth": dd})
            # 跳过本次事件覆盖的区间，避免重叠
            i = lo_idx + WINDOW
        else:
            i += 1
    return [dict(e, code=code, name=name) for e in events]


def measure(df: pd.DataFrame, ev: dict, bench: pd.DataFrame) -> dict | None:
    p, l = ev["peak_idx"], ev["low_idx"]
    seg = df.iloc[p : l + 1]
    if seg.empty:
        return None
    low_close = float(df["close"].iloc[l])
    peak_close = float(df["close"].iloc[p])
    days = l - p

    # —— 修复（因变量，仅供分层比较，不构成预测）——
    after = df.iloc[l + 1 :]
    if len(after) < HOLD_DAYS:
        return None
    fwd20 = (float(after["close"].iloc[HOLD_DAYS - 1]) / low_close - 1) * 100
    fwd40 = (float(after["close"].iloc[min(39, len(after) - 1)]) / low_close - 1) * 100
    max_up = (float(after["close"].max()) / low_close - 1) * 100

    # —— 形态特征（自变量）——
    rets = seg["ret"].iloc[1:]
    worst = float(rets.min()) if len(rets) else np.nan
    n_down2 = int((rets <= -2).sum())
    n_down3 = int((rets <= -3).sum())
    up_ratio = float((rets > 0).mean()) if len(rets) else np.nan

    # 量能：跌期间均量 / 跌之前 20 日均量
    pre = df.iloc[max(0, p - 20) : p]
    base_vol = float(pre["volume"].mean()) if len(pre) else np.nan
    vol_ratio = float(seg["volume"].mean()) / base_vol if base_vol else np.nan

    # 波动放大
    pre_std = float(pre["ret"].std()) if len(pre) > 1 else np.nan
    vola = float(rets.std()) / pre_std if pre_std else np.nan

    # 同步市场：同区间沪深300 涨跌
    d0 = df["date"].iloc[p]
    d1 = df["date"].iloc[l]
    b0 = bench[bench["date"] <= d0]["close"].iloc[-1]
    b1 = bench[bench["date"] <= d1]["close"].iloc[-1]
    bench_ret = (b1 / b0 - 1) * 100
    excess = (low_close / peak_close - 1) * 100 - bench_ret

    row = df.iloc[l]
    ma20_gap = (low_close / row["ma20"] - 1) * 100 if row["ma20"] == row["ma20"] else np.nan
    ma60_gap = (low_close / row["ma60"] - 1) * 100 if row["ma60"] == row["ma60"] else np.nan

    return {
        "code": ev["code"], "name": ev["name"],
        "low_date": str(df["date"].iloc[l].date()),
        "depth%": round((low_close / peak_close - 1) * 100, 2),
        "days": days,
        "dayrate%": round((low_close / peak_close - 1) * 100 / max(days, 1), 2),
        "最大单日跌%": round(worst, 2),
        "跌>2%天": n_down2, "跌>3%天": n_down3,
        "上涨日占比": round(up_ratio, 2),
        "量能比": round(vol_ratio, 2),
        "波动放大": round(vola, 2),
        "同期300%": round(bench_ret, 2),
        "超额%": round(excess, 2),
        "离MA20%": round(ma20_gap, 2),
        "离MA60%": round(ma60_gap, 2),
        f"后{HOLD_DAYS}日%": round(fwd20, 2),
        "后40日%": round(fwd40, 2),
        "后最大涨%": round(max_up, 2),
    }


def main() -> None:
    bench = load("510300")
    uni = pd.read_csv(ROOT / "etf_universe.csv", dtype={"代码": str})
    name_map = {str(r["代码"]).zfill(6): str(r["名称"]) for _, r in uni.iterrows()}

    rows: list[dict] = []
    used = 0
    for p in sorted(RAW.glob("*.csv")):
        code = p.stem
        if not code.isdigit():
            continue
        df = load(code)
        if df is None:
            continue
        used += 1
        evs = find_events(df, code, name_map.get(code, code))
        for ev in evs:
            m = measure(df, ev, bench)
            if m:
                rows.append(m)

    out = pd.DataFrame(rows)
    out.to_csv(ROOT / "events.csv", index=False, encoding="utf-8-sig")

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 60)
    print(f"扫描标的 {used} 只，急跌事件 {len(out)} 个（阈值 {DEPTH_THRESHOLD}%/ {WINDOW}日内）")
    print(f"时间跨度：{out['low_date'].min()} ~ {out['low_date'].max()}")
    print(f"\n=== 修复分布（后{HOLD_DAYS}日收益 %）===")
    print(out[f"后{HOLD_DAYS}日%"].describe(percentiles=[.1, .25, .5, .75, .9]).round(2).to_string())
    print(f"\n=== 修复分布（后最大涨 %）===")
    print(out["后最大涨%"].describe(percentiles=[.1, .25, .5, .75, .9]).round(2).to_string())

    # 分层：每个特征分 3 组，看修复差异
    feats = ["depth%", "days", "dayrate%", "最大单日跌%", "跌>2%天", "跌>3%天",
             "上涨日占比", "量能比", "波动放大", "同期300%", "超额%", "离MA20%", "离MA60%"]
    print(f"\n=== 分层比较：按特征三分位，看后{HOLD_DAYS}日收益中位数 与 后最大涨中位数 ===")
    res = []
    for f in feats:
        s = out[f]
        try:
            g = pd.qcut(s, 3, labels=["低", "中", "高"], duplicates="drop")
        except ValueError:
            continue
        agg = out.groupby(g, observed=True).agg(
            n=(f"后{HOLD_DAYS}日%", "size"),
            fwd20=(f"后{HOLD_DAYS}日%", "median"),
            maxup=("后最大涨%", "median"),
        ).round(2)
        res.append((f, agg))
        print(f"\n--- {f}")
        print(agg.to_string())
        print(f"    极差(后{HOLD_DAYS}日) = {round(agg['fwd20'].max()-agg['fwd20'].min(),2)}pp"
              f" | 极差(后最大涨) = {round(agg['maxup'].max()-agg['maxup'].min(),2)}pp")

    # 汇总极差排序
    print("\n=== 各特征区分力排序（后最大涨 三分位中位数极差，越大越强）===")
    rank = []
    for f, agg in res:
        rank.append((f, round(agg["maxup"].max() - agg["maxup"].min(), 2),
                     round(agg["fwd20"].max() - agg["fwd20"].min(), 2)))
    for f, a, b in sorted(rank, key=lambda x: -x[1]):
        print(f"  {f:<12} 后最大涨极差 {a:>6}pp   后20日极差 {b:>6}pp")


if __name__ == "__main__":
    main()

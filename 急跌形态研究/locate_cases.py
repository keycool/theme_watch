"""修正版：用局部极值法重新检测事件，把客户甲的案例放回全样本分布定位。

主因变量改为「后最大涨%」——因为客户甲说的"回升"指的是反弹幅度，
而不是后 20 日的落点收益（这两者在本样本里排序并不一致）。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"

DEPTH = -10.0
WINDOW = 20
HOLD = 20

CASES = [
    ("159915", "创业板ETF", "2026-07-30"),
    ("588050", "科创50ETF", "2026-08-03"),
    ("563300", "中证2000ETF", "2026-07-20"),
    ("515180", "红利ETF", "2026-06-29"),
    ("512890", "红利低波ETF", "2026-06-29"),
    ("512010", "医药ETF", "2026-06-09"),
    ("512170", "医疗ETF", "2026-06-09"),
    ("159992", "创新药ETF", "2026-06-09"),
    ("515220", "煤炭ETF", "2026-06-30"),
    ("159611", "电力ETF", "2026-07-09"),
]


def load(code: str) -> pd.DataFrame | None:
    p = RAW / f"{code}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    if len(df) < 60:
        return None
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df["ret"] = df["close"].pct_change() * 100
    for n in (20, 60):
        df[f"ma{n}"] = df["close"].rolling(n).mean()
    return df


def all_events(df: pd.DataFrame, bench: pd.DataFrame, code: str, name: str) -> list[dict]:
    """局部极值法：i 是过去 WINDOW 日内最低收盘 且 回撤达标 且 后 3 日不再创新低。"""
    n = len(df)
    close = df["close"].values
    out = []
    for i in range(WINDOW, n - HOLD):
        seg = close[i - WINDOW : i + 1]
        lo = close[i]
        if lo > min(seg):
            continue  # i 不是窗口最低
        hi = max(seg)
        if hi <= 0:
            continue
        dd = (lo / hi - 1) * 100
        if dd > DEPTH:
            continue
        # 后 3 日不再创新低（确认是局部底）
        nxt = close[i + 1 : i + 4]
        if len(nxt) and nxt.min() < lo:
            continue
        # 特征
        seg_df = df.iloc[int(np.argmax(seg)) + i - WINDOW : i + 1]
        rets = seg_df["ret"].iloc[1:]
        worst = float(rets.min()) if len(rets) else np.nan
        n2 = int((rets <= -2).sum())
        n3 = int((rets <= -3).sum())
        peak_i = int(np.argmax(seg)) + i - WINDOW
        pre = df.iloc[max(0, peak_i - 20) : peak_i]
        bv = float(pre["volume"].mean()) if len(pre) else np.nan
        vr = float(seg_df["volume"].mean()) / bv if bv else np.nan
        ps = float(pre["ret"].std()) if len(pre) > 1 else np.nan
        va = float(rets.std()) / ps if ps else np.nan
        d0, d1 = df["date"].iloc[peak_i], df["date"].iloc[i]
        b0 = bench[bench["date"] <= d0]["close"].iloc[-1]
        b1 = bench[bench["date"] <= d1]["close"].iloc[-1]
        bret = (b1 / b0 - 1) * 100
        row = df.iloc[i]
        after = df.iloc[i + 1 :]
        out.append({
            "code": code, "name": name,
            "low_date": str(d1.date()),
            "depth%": round(dd, 2),
            "days": i - peak_i,
            "最大单日跌%": round(worst, 2),
            "跌>2%天": n2, "跌>3%天": n3,
            "上涨日占比": round(float((rets > 0).mean()), 2) if len(rets) else np.nan,
            "量能比": round(vr, 2), "波动放大": round(va, 2),
            "同期300%": round(bret, 2),
            "超额%": round(dd - bret, 2),
            "离MA60%": round((lo / row["ma60"] - 1) * 100, 2) if row["ma60"] == row["ma60"] else np.nan,
            f"后{HOLD}日%": round((float(after["close"].iloc[HOLD - 1]) / lo - 1) * 100, 2),
            "后最大涨%": round((float(after["close"].max()) / lo - 1) * 100, 2),
        })
    return out


def main() -> None:
    bench = load("510300")
    uni = pd.read_csv(ROOT / "etf_universe.csv", dtype={"代码": str})
    nm = {str(r["代码"]).zfill(6): str(r["名称"]) for _, r in uni.iterrows()}
    for code, name, _ in CASES:
        nm.setdefault(code, name)

    rows = []
    for p in sorted(RAW.glob("*.csv")):
        code = p.stem
        if not code.isdigit():
            continue
        df = load(code)
        if df is None:
            continue
        rows += all_events(df, bench, code, nm.get(code, code))
    ev = pd.DataFrame(rows)
    ev.to_csv(ROOT / "events_v2.csv", index=False, encoding="utf-8-sig")
    print(f"重检后事件数 {len(ev)}（局部极值法）")

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)

    print("\n=== 一、全样本修复分布 ===")
    for c in [f"后{HOLD}日%", "后最大涨%"]:
        s = ev[c]
        print(f"{c}: 中位 {s.median():.2f} | 均值 {s.mean():.2f} | "
              f"P25 {s.quantile(.25):.2f} | P75 {s.quantile(.75):.2f} | "
              f"上涨占比 {(s > 0).mean() * 100:.0f}%")

    print("\n=== 二、客户甲案例定位（分位 50 = 全样本中位）===")
    res = []
    for code, name, date in CASES:
        d = pd.Timestamp(date)
        c = ev[(ev["code"].astype(str) == code) & (ev["low_date"].apply(lambda x: abs((pd.Timestamp(x) - d).days)) <= 5)]
        if c.empty:
            res.append({"name": name, "note": "未检出事件"})
            continue
        r = c.iloc[c["depth%"].argmin()]
        res.append({
            "name": name, "低点日": r["low_date"], "跌幅%": r["depth%"],
            "天数": r["days"], "最大单日跌%": r["最大单日跌%"],
            "跌>3%天": r["跌>3%天"], "量能比": r["量能比"],
            "同期300%": r["同期300%"], "超额%": r["超额%"], "离MA60%": r["离MA60%"],
            f"后{HOLD}日%": r[f"后{HOLD}日%"],
            "后20日分位": round((ev[f"后{HOLD}日%"] < r[f"后{HOLD}日%"]).mean() * 100),
            "后最大涨%": r["后最大涨%"],
            "后最大涨分位": round((ev["后最大涨%"] < r["后最大涨%"]).mean() * 100),
        })
    print(pd.DataFrame(res).to_string(index=False))

    print("\n=== 三、以「后最大涨%」为因变量的分层（三分位中位数）===")
    feats = ["depth%", "days", "最大单日跌%", "跌>2%天", "跌>3%天", "上涨日占比",
             "量能比", "波动放大", "同期300%", "超额%", "离MA60%"]
    rank = []
    for f in feats:
        try:
            g = pd.qcut(ev[f], 3, labels=["低", "中", "高"], duplicates="drop")
        except ValueError:
            continue
        a = ev.groupby(g, observed=True).agg(n=("后最大涨%", "size"), maxup=("后最大涨%", "median"),
                                             fwd=(f"后{HOLD}日%", "median")).round(2)
        mono = a["maxup"].is_monotonic_increasing or a["maxup"].is_monotonic_decreasing
        rank.append((f, round(a["maxup"].max() - a["maxup"].min(), 2), "单调" if mono else "非单调(噪音?)"))
        print(f"\n--- {f}")
        print(a.to_string())
    print("\n=== 区分力排序 ===")
    for f, r, m in sorted(rank, key=lambda x: -x[1]):
        print(f"  {f:<12} 极差 {r:>6}pp   {m}")


if __name__ == "__main__":
    main()

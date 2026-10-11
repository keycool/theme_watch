"""量化「事后看图」带来的幻觉：无前视触发 vs 事后确认底部。

定义 A（无前视 / 真实可触发）
    当日收盘 相对 过去 20 日最高收盘 回撤 >= 10%，当日即为触发日。
    不要求后面不再跌——触发之后继续跌是常态，这才是不含未来信息的口径。

定义 B（前视 / 事后确认）
    在 A 的基础上，额外要求「后 3 个交易日不再创新低」。
    这是看图复盘时人脑自动做的事：只把那些"确实是底"的点当成底。

两者后续收益的差距，就是「事后看图」的幻觉幅度。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
DEPTH = -10.0
WIN = 20
HOLD = 20


def load(code: str) -> pd.DataFrame | None:
    p = RAW / f"{code}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    if len(df) < 80:
        return None
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def scan(df: pd.DataFrame, confirm: bool) -> list[dict]:
    close = df["close"].values
    n = len(close)
    out = []
    i = WIN
    while i < n - HOLD:
        seg = close[i - WIN : i + 1]
        hi = seg.max()
        lo = close[i]
        dd = (lo / hi - 1) * 100
        if dd <= DEPTH:
            if confirm:
                nxt = close[i + 1 : i + 4]
                if len(nxt) and nxt.min() < lo:
                    i += 1
                    continue
            fwd20 = (close[i + HOLD] / lo - 1) * 100
            maxup = (close[i + 1 : i + 1 + min(40, n - i - 1)].max() / lo - 1) * 100
            out.append({"date": str(df["date"].iloc[i].date()), "dd": dd,
                        "fwd20": fwd20, "maxup": maxup,
                        "worse": (close[i + 1 : i + 6].min() / lo - 1) * 100})
            i += WIN  # 同一波不重复计数
        else:
            i += 1
    return out


def main() -> None:
    rows_a, rows_b = [], []
    for p in sorted(RAW.glob("*.csv")):
        code = p.stem
        if not code.isdigit():
            continue
        df = load(code)
        if df is None:
            continue
        rows_a += [dict(r, code=code) for r in scan(df, confirm=False)]
        rows_b += [dict(r, code=code) for r in scan(df, confirm=True)]
    a, b = pd.DataFrame(rows_a), pd.DataFrame(rows_b)

    pd.set_option("display.width", 200)
    print(f"定义 A（无前视，触发即计）：{len(a)} 个事件")
    print(f"定义 B（事后确认底部）：    {len(b)} 个事件\n")

    print("=== 核心对照：同一批数据，两种口径的「后续收益」===")
    cmp_rows = []
    for label, d in [("A 触发即计（真实）", a), ("B 事后确认（看图）", b)]:
        s20, smax = d["fwd20"], d["maxup"]
        cmp_rows.append({
            "口径": label, "事件数": len(d),
            "后20日中位%": round(s20.median(), 2),
            "后20日均值%": round(s20.mean(), 2),
            "后20日为负占比%": round((s20 < 0).mean() * 100, 0),
            "后40日最大涨中位%": round(smax.median(), 2),
            "最大涨>15%占比%": round((smax > 15).mean() * 100, 0),
        })
    print(pd.DataFrame(cmp_rows).to_string(index=False))

    print("\n=== 触发后还会跌多深？（定义 A，触发日 -> 之后 5 日内最低）===")
    w = a["worse"]
    print(f"中位数 {w.median():.2f}% | 均值 {w.mean():.2f}% | "
          f"继续跌 >2% 的占比 {(w < -2).mean()*100:.0f}% | 继续跌 >5% 的占比 {(w < -5).mean()*100:.0f}%")
    print(">>> 这才是「急跌触发当天」真实面临的情况：多数还要再跌一段。")

    print("\n=== 按触发日所在月份看（定义 A）===")
    a["ym"] = a["date"].str.slice(0, 7)
    m = a.groupby("ym").agg(n=("fwd20", "size"), fwd20=("fwd20", "median"), maxup=("maxup", "median")).round(2)
    print(m.to_string())
    print(">>> 月份之间差异巨大 = 「什么时候跌」比「怎么跌」重要得多。")

    a.to_csv(ROOT / "events_no_lookahead.csv", index=False, encoding="utf-8-sig")
    b.to_csv(ROOT / "events_confirmed.csv", index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()

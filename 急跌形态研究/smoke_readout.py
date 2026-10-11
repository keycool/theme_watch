"""对 drawdown_readout.compute_drawdown 做冒烟 + 边界验证（只读 raw/，不写产物）。"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from drawdown_readout import compute_drawdown

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"


def load(code: str) -> pd.DataFrame:
    df = pd.read_csv(RAW / f"{code}.csv")
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df.sort_values("date").reset_index(drop=True)


def main() -> None:
    bench = load("510300")
    bd = bench["date"].tolist()
    bc = bench["close"].tolist()

    # ---- 1. 客户甲案例：截取到各自的低点日 ----
    print("=== 1. 客户甲案例（截止各自的低点日）===")
    cases = [
        ("159915", "创业板ETF", "2026-07-30"),
        ("588050", "科创50ETF", "2026-08-03"),
        ("159611", "电力ETF", "2026-07-13"),
        ("512010", "医药ETF", "2026-06-09"),
    ]
    for code, name, asof in cases:
        df = load(code)
        sub = df[df["date"] <= asof]
        r = compute_drawdown(
            sub["date"].tolist(), sub["close"].tolist(), sub["volume"].tolist(),
            bd, bc,
        )
        print(f"\n--- {name} {code} @ {asof}")
        print(json.dumps(r, ensure_ascii=False, indent=2))

    # ---- 2. 边界：数据不足 ----
    print("\n=== 2. 边界情况 ===")
    empty = compute_drawdown([], [])
    print(f"空序列: asOf={empty['asOf']} triggered={empty['triggered']} dd={empty['drawdownPct']}")
    one = compute_drawdown(["2026-01-05"], [1.0])
    print(f"单根K线: triggered={one['triggered']} dd={one['drawdownPct']} days={one['drawdownDays']}")
    three = compute_drawdown(["a", "b", "c"], [10.0, 9.0, 8.8], [100, 110, 90])
    print(f"三根K线: dd={three['drawdownPct']}% windowDays={three['windowDays']} "
          f"input CTR={three['downDaysOver2Pct']} vol={three['volumeRatio']}")

    # ---- 3. 阈值边界 ----
    print("\n=== 3. 阈值边界（恰好 -10%）===")
    cs = [10.0] + [10.0] * 18 + [9.0]  # 最后一根恰好 -10%
    ds = [f"d{i}" for i in range(len(cs))]
    r10 = compute_drawdown(ds, cs)
    print(f"恰好-10%: dd={r10['drawdownPct']} triggered={r10['triggered']}  (阈值含等于 -> 应为 True)")
    cs2 = [10.0] + [10.0] * 18 + [9.01]
    r09 = compute_drawdown(ds, cs2)
    print(f"-9.9%:    dd={r09['drawdownPct']} triggered={r09['triggered']}  (应为 False)")

    # ---- 4. 幂等：同一份数据连算两次必须一致 ----
    print("\n=== 4. 幂等性 ===")
    df = load("159915")
    sub = df[df["date"] <= "2026-07-30"]
    args = (sub["date"].tolist(), sub["close"].tolist(), sub["volume"].tolist(), bd, bc)
    a = compute_drawdown(*args)
    b = compute_drawdown(*args)
    print(f"两次调用完全一致: {json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)}")

    # ---- 5. 无副作用声明检查：不应产生任何新文件 ----
    before = set(p.name for p in ROOT.iterdir())
    compute_drawdown(*args)
    after = set(p.name for p in ROOT.iterdir())
    print(f"\n=== 5. 无副作用: 调用前后目录差异 = {sorted(after - before)} (应为空)")

    print("\n全部冒烟检查完成。")


if __name__ == "__main__":
    main()

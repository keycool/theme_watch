"""检查事件独立性 + 把客户甲的案例放回全样本分布里定位。

两件事：
1. 事件按 low_date 聚类——同一波市场下杀会同时触发几十只 ETF，
   这些事件不是独立样本。量化「独立时间簇」有多少个。
2. 客户甲的 10 个案例在 449 个事件的分位数，看它们是不是幸存者。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent

CASES = {
    "159915": ("创业板ETF", "2026-07-30"),
    "588050": ("科创50ETF", "2026-08-03"),
    "563300": ("中证2000ETF", "2026-07-20"),
    "515180": ("红利ETF", "2026-06-29"),
    "512890": ("红利低波ETF", "2026-06-29"),
    "512010": ("医药ETF", "2026-06-09"),
    "512170": ("医疗ETF", "2026-06-09"),
    "159992": ("创新药ETF", "2026-06-09"),
    "515220": ("煤炭ETF", "2026-06-30"),
    "159611": ("电力ETF", "2026-07-09"),
}


def main() -> None:
    df = pd.read_csv(ROOT / "events.csv")
    df["low_date"] = pd.to_datetime(df["low_date"])

    # ---------- 1. 时间聚类 ----------
    print("=== 一、事件的时间分布（独立性检验）===")
    by_date = df.groupby("low_date").size().sort_values(ascending=False)
    print(f"事件总数 {len(df)}，分布在 {len(by_date)} 个不同日期")
    print(f"单日最多 {by_date.max()} 个事件")
    print("\nTop 15 日期（同一天触发多少只 ETF）：")
    print(by_date.head(15).to_string())

    # 按 5 个交易日窗口聚类
    df2 = df.sort_values("low_date").copy()
    cluster_id = 0
    prev = None
    ids = []
    for d in df2["low_date"]:
        if prev is None or (d - prev).days > 7:
            cluster_id += 1
        prev = d
        ids.append(cluster_id)
    df2["cluster"] = ids
    nc = df2["cluster"].nunique()
    sizes = df2.groupby("cluster").size()
    print(f"\n按「相邻 <=7 自然日」聚类：{nc} 个独立时间簇")
    print(f"  每簇事件数：中位数 {sizes.median():.0f}，最大 {sizes.max()}，最小 {sizes.min()}")
    print(f"  含 >=10 个事件的簇：{(sizes >= 10).sum()} 个，覆盖 {sizes[sizes >= 10].sum()} 个事件（{sizes[sizes>=10].sum()/len(df)*100:.0f}%）")
    print("\n>>> 统计口径警告：有效独立样本 ≈ 时间簇数量，而不是事件数量。")

    # 簇内 vs 簇间方差分解（粗略）：用后20日收益
    g = df2.groupby("cluster")[f"后20日%"].agg(["mean", "size"])
    within = df2.groupby("cluster")[f"后20日%"].transform("mean")
    total_var = df2[f"后20日%"].var()
    between_var = (within - df2[f"后20日%"].mean()).var()
    print(f"\n后20日收益：总方差 {total_var:.1f}，其中「簇间」解释 {between_var:.1f} "
          f"（{between_var/total_var*100:.0f}%）")
    print(">>> 簇间占比越高 = 越是被「什么时候跌」决定，而不是「怎么跌」。")

    # ---------- 2. 客户甲案例定位 ----------
    print("\n=== 二、客户甲的 10 个案例在全样本里的位置 ===")
    rows = []
    for code, (name, date) in CASES.items():
        d = pd.Timestamp(date)
        cand = df[(df["code"].astype(str) == code) & (df["low_date"].sub(d).abs().dt.days <= 3)]
        if cand.empty:
            rows.append({"name": name, "code": code, "note": "全样本中未匹配到事件"})
            continue
        r = cand.iloc[0]
        fwd = f"后20日%"
        pct_rank = (df[fwd] < r[fwd]).mean() * 100
        pct_rank_max = (df["后最大涨%"] < r["后最大涨%"]).mean() * 100
        rows.append({
            "name": name, "code": code,
            "低点日": str(r["low_date"].date()),
            "跌幅%": r["depth%"],
            "同期300%": r["同期300%"],
            "超额%": r["超额%"],
            "离MA60%": r["离MA60%"],
            "后20日%": r[fwd],
            "后20日分位": round(pct_rank, 0),
            "后最大涨%": r["后最大涨%"],
            "后最大涨分位": round(pct_rank_max, 0),
        })
    out = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    print(out.to_string(index=False))
    print("\n分位说明：50 = 全样本中位数。>50 表示比半数事件修复得好。")


if __name__ == "__main__":
    main()

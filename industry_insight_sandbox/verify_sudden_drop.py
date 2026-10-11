#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
急跌 vs 阴跌 —— 历史验证脚本（纯观察，不改任何策略判定）

命题（客户甲 2026-09-18 提出）：
    「找那些一路延续、但突然急跌的（流动性/负面消息/被抽血），而不是一路阴跌的
      （行业逻辑坏了）。」
    隐含假设：急跌是外生冲击 -> 会修复；阴跌是内生恶化 -> 不修复。

本脚本要回答的唯一问题：
    **在「20 个交易日前还在 MA60 上方」的样本里，下跌的「速度」（z5）与
      之后的 5/10/20/60 日收益，是单调正相关（修复）还是单调负相关（续跌）？**

设计要点
--------
1. 只做分桶，不做二分类。z5 分 7 档，看剂量-反应曲线是否单调。
   客户甲的假设成立 => 最负的 z5 桶前向收益最好（均值回归）。
   假设不成立 => 最负的 z5 桶前向收益最差（动量续跌 / 逻辑真坏了）。
2. z5 = 5 日收益 / (跌前 60 日日均波动 σ × √5)。
   σ 取跌前窗口 [t-64, t-5]，不把暴跌本身算进去 —— 否则"突然"会被自己的
   波动稀释。同时输出 σ 含暴跌的版本做敏感性对照。
3. 三重基准，缺一不可：
   - 绝对收益
   - 超额 vs 沪深300（去掉市场方向）
   - 超额 vs 横截面中位数（同一天、同一期限、全池中位）——去掉市场+风格 Beta，
     这才是"被抽血后是否相对修复"的正确度量。
4. 同一标的事件冷却 20 个交易日，避免一次暴跌被切成 10 个样本。
5. 熔断/股灾日（同一天触发数 >= 5）单独标记，敏感性分析里剔除，
   防止 2015/2016/2020 几个市场级事件主导结论。

输出：backtest_results/sudden_drop_events.csv
      backtest_results/sudden_drop_summary.md

归档状态：2026-09-21 客户甲拍板 A（就此停下）。
本脚本为一次性历史验证，已冻结为档案，不再继续试新的急跌定义。
唯一被采纳的结论（全市场一起跌 vs 单独被砸）已并入观察层观察读数。
"""

from __future__ import annotations

import argparse
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "backtest_cache"
PRODUCTION_CACHE_DIR = DATA_DIR / "cache"
RESULTS = ROOT / "backtest_results"

FILE_RE = re.compile(
    r"^(daily|fund_daily|index_daily|stock_daily|hk_daily)_([0-9]{6})_([A-Z]{2,3})_(\d{8})_(\d{8})\.csv$"
)

# 宽基指数：不属于"行业/主题"，主测试里默认剔除
BROAD_INDEX = {
    "000001.SH", "000300.SH", "000016.SH", "000905.SH", "000852.SH",
    "000906.SH", "000010.SH", "000009.SH", "000903.SH", "399001.SZ",
    "399006.SZ", "399300.SZ", "399005.SZ", "399106.SZ", "000985.CSI",
    "000015.SH", "000012.SH", "000013.SH", "000018.SH", "000019.SH",
}

UNIVERSE_KINDS = {
    "index": ("index_daily",),
    "etf": ("fund_daily",),
    "stock": ("daily", "stock_daily"),
    "all": ("index_daily", "fund_daily", "daily", "stock_daily"),
}

# 分桶边界（z5，均为负值方向）
Z_BUCKETS = [
    ("z<=-2.0", lambda z: z <= -2.0),
    ("-2.0<z<=-1.5", lambda z: -2.0 < z <= -1.5),
    ("-1.5<z<=-1.2", lambda z: -1.5 < z <= -1.2),
    ("-1.2<z<=-0.8", lambda z: -1.2 < z <= -0.8),
    ("-0.8<z<=-0.4", lambda z: -0.8 < z <= -0.4),
    ("-0.4<z<=0", lambda z: -0.4 < z <= 0.0),
    ("z>0", lambda z: z > 0.0),
]

FORWARD_HORIZONS = (5, 10, 20, 60)
COOLDOWN_DAYS = 20
MARKET_WIDE_TRIGGER_COUNT = 5   # 同一自然日触发数 >= 此值，视为市场级冲击


# --------------------------------------------------------------------------- #
# 数据加载
# --------------------------------------------------------------------------- #
def build_cache_index(kinds: tuple[str, ...]) -> dict[str, Path]:
    """同一代码可能有多份不同区间/不同日期的缓存，取行数最多的那份。"""
    best: dict[str, tuple[int, Path]] = {}
    for directory in (CACHE_DIR, PRODUCTION_CACHE_DIR):
        if not directory.exists():
            continue
        for path in directory.glob("*.csv"):
            if any(k in path.name for k in ("weight", "basic", "metadata")):
                continue
            m = FILE_RE.match(path.name)
            if not m:
                continue
            kind, code, market = m.group(1), m.group(2), m.group(3)
            if kind not in kinds:
                continue
            try:
                rows = sum(1 for _ in path.open("r", encoding="utf-8-sig")) - 1
            except Exception:
                rows = 0
            key = f"{code}.{market}"
            if key not in best or rows > best[key][0]:
                best[key] = (rows, path)
    return {k: v[1] for k, v in best.items()}


def load_series(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig")
    if "trade_date" not in frame:
        return pd.DataFrame()
    frame["trade_date"] = frame["trade_date"].astype(str).str.replace("-", "")
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna(subset=["close"])
    frame = frame.drop_duplicates("trade_date", keep="last").sort_values("trade_date")
    return frame.reset_index(drop=True)


def add_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    ret = out["close"].pct_change()
    out["ma60"] = out["close"].rolling(60).mean()
    out["ma250"] = out["close"].rolling(250).mean()
    out["ret5"] = out["close"].pct_change(5)
    out["ret20"] = out["close"].pct_change(20)
    out["ret60"] = out["close"].pct_change(60)
    # 跌前波动：[t-64, t-5]，不含暴跌本身
    out["sigma_pre"] = ret.rolling(60).std().shift(5)
    # 含暴跌的滚动波动（敏感性对照）
    out["sigma_trail"] = ret.rolling(60).std()
    out["z5"] = out["ret5"] / (out["sigma_pre"] * math.sqrt(5))
    out["z5_trail"] = out["ret5"] / (out["sigma_trail"] * math.sqrt(5))
    out["high60"] = out["close"].rolling(60).max()
    out["dd_from_high60"] = out["close"] / out["high60"] - 1.0
    for h in FORWARD_HORIZONS:
        out[f"fwd{h}"] = out["close"].shift(-h) / out["close"] - 1.0
    # 20 日内最坏回撤（相对信号日收盘）
    future = out["close"].iloc[::-1]
    out["mae20"] = np.nan
    closes = out["close"].to_numpy()
    n = len(closes)
    mae = np.full(n, np.nan)
    for i in range(n - 1):
        window = closes[i + 1: min(i + 21, n)]
        if window.size:
            mae[i] = window.min() / closes[i] - 1.0
    out["mae20"] = mae
    return out


# --------------------------------------------------------------------------- #
# 事件抽取
# --------------------------------------------------------------------------- #
def collect_events(
    code: str,
    frame: pd.DataFrame,
    require_trend: bool,
    min_drop: float | None,
) -> tuple[list[dict], pd.DataFrame, pd.Series]:
    """返回 (事件列表, 该标的前向收益表, 该标的 ret5 序列)。"""
    if len(frame) < 300:
        return [], pd.DataFrame(), pd.Series(dtype=float)

    closes = frame["close"].to_numpy()
    ma60 = frame["ma60"].to_numpy()
    ret5 = frame["ret5"].to_numpy()
    ret60 = frame["ret60"].to_numpy()
    z5 = frame["z5"].to_numpy()
    z5t = frame["z5_trail"].to_numpy()
    dd = frame["dd_from_high60"].to_numpy()
    dates = frame["trade_date"].to_numpy()
    fwd = {h: frame[f"fwd{h}"].to_numpy() for h in FORWARD_HORIZONS}
    mae20 = frame["mae20"].to_numpy()

    events: list[dict] = []
    last_idx: int | None = None
    for i in range(250, len(frame) - 60):  # 留足 MA250 与 60 日前向窗口
        z = z5[i]
        if z is None or not np.isfinite(z):
            continue
        above60_prev = ma60[i - 20]
        if not np.isfinite(above60_prev) or closes[i - 20] <= above60_prev:
            continue
        if require_trend:
            r60 = ret60[i]
            if not np.isfinite(r60) or r60 <= 0:
                continue
        if min_drop is not None and (not np.isfinite(ret5[i]) or ret5[i] > min_drop):
            continue
        if last_idx is not None and i - last_idx < COOLDOWN_DAYS:
            # 冷却期内直接跳过（取窗口内【第一个】触发日，不取最极端）。
            # 早期版本取"最极端"，结果把每个窗口都逼出一个急跌样本，
            # z5 分布被人为压向负值（实测 55% 落入 z5<=-1.2），剂量-反应失效。
            continue
        last_idx = i

        row = {
            "code": code,
            "date": dates[i],
            "z5": float(z),
            "z5_trail": float(z5t[i]) if np.isfinite(z5t[i]) else None,
            "ret5": float(ret5[i]) if np.isfinite(ret5[i]) else None,
            "ret20": float(frame["ret20"].to_numpy()[i]),
            "ret60": float(ret60[i]) if np.isfinite(ret60[i]) else None,
            "dd_from_high60": float(dd[i]) if np.isfinite(dd[i]) else None,
            "above_ma60_now": bool(closes[i] > ma60[i]) if np.isfinite(ma60[i]) else None,
            "mae20": float(mae20[i]) if np.isfinite(mae20[i]) else None,
        }
        pre = closes[i - 5]  # 暴跌前的收盘（完整往返的起点）
        for h in FORWARD_HORIZONS:
            v = fwd[h][i]
            row[f"fwd{h}"] = float(v) if np.isfinite(v) else None
            if h + i < len(closes) and pre and np.isfinite(pre) and pre > 0:
                row[f"round{h}"] = float(closes[i + h] / pre - 1.0)
            else:
                row[f"round{h}"] = None
        events.append(row)

    fwd_table = frame[["trade_date"] + [f"fwd{h}" for h in FORWARD_HORIZONS]].copy()
    fwd_table = fwd_table.set_index("trade_date")
    fwd_table.columns = [f"{code}|{c}" for c in fwd_table.columns]
    ret5_series = frame.set_index("trade_date")["ret5"].rename(code)
    return events, fwd_table, ret5_series


def bucket_of(z: float) -> str:
    for name, test in Z_BUCKETS:
        if test(z):
            return name
    return "?"


# --------------------------------------------------------------------------- #
# 汇总
# --------------------------------------------------------------------------- #
def _fmt(v: float | None, pct: bool = True, nd: int = 2) -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "—"
    return f"{v * 100:.{nd}f}%" if pct else f"{v:.{nd}f}"


def _stats(values: list[float]) -> dict:
    arr = np.array([v for v in values if v is not None and np.isfinite(v)])
    if arr.size == 0:
        return {"n": 0}
    return {
        "n": int(arr.size),
        "median": float(np.median(arr)),
        "mean": float(arr.mean()),
        "p25": float(np.percentile(arr, 25)),
        "p75": float(np.percentile(arr, 75)),
        "win": float((arr > 0).mean()),
        "std": float(arr.std(ddof=1)) if arr.size > 1 else 0.0,
    }


def clustered_bootstrap_median_diff(
    group_a: list[dict],
    group_b: list[dict],
    metric: str,
    n_boot: int = 2000,
    seed: int = 20260918,
) -> tuple[float, float, float]:
    """按【日期】整块重抽的 bootstrap —— 事件在同一天上高度相关，
    逐事件重抽会把显著性夸大好几倍，必须按日期聚类。"""
    rng = np.random.default_rng(seed)
    a_by_date: dict[str, list[float]] = defaultdict(list)
    b_by_date: dict[str, list[float]] = defaultdict(list)
    for e in group_a:
        v = e.get(metric)
        if v is not None and np.isfinite(v):
            a_by_date[e["date"]].append(v)
    for e in group_b:
        v = e.get(metric)
        if v is not None and np.isfinite(v):
            b_by_date[e["date"]].append(v)
    dates = sorted(set(a_by_date) | set(b_by_date))
    if len(dates) < 30:
        return (float("nan"), float("nan"), float("nan"))

    def med_of(mapping: dict, keys) -> float:
        vals = [v for k in keys for v in mapping.get(k, [])]
        return float(np.median(vals)) if vals else float("nan")

    diffs = []
    for _ in range(n_boot):
        sample = rng.choice(dates, size=len(dates), replace=True)
        ma, mb = med_of(a_by_date, sample), med_of(b_by_date, sample)
        if np.isfinite(ma) and np.isfinite(mb):
            diffs.append(ma - mb)
    if not diffs:
        return (float("nan"), float("nan"), float("nan"))
    lo, hi = np.percentile(diffs, [5, 95])
    return (float(np.mean(diffs)), float(lo), float(hi))


def main() -> None:
    parser = argparse.ArgumentParser(description="急跌 vs 阴跌 历史验证")
    parser.add_argument("--universe", default="index", choices=sorted(UNIVERSE_KINDS))
    parser.add_argument("--exclude-broad", action="store_true", default=False,
                        help="剔除宽基指数（仅 index 池有意义）")
    parser.add_argument("--require-trend", action="store_true", default=True)
    parser.add_argument("--no-require-trend", dest="require_trend", action="store_false")
    parser.add_argument("--min-drop", type=float, default=-0.03,
                        help="5 日跌幅下限（如 -0.03 表示至少跌 3%）；设 0 关闭")
    parser.add_argument("--min-rows", type=int, default=1500)
    parser.add_argument("--output-tag", default="")
    args = parser.parse_args()

    min_drop = None if args.min_drop == 0 else args.min_drop

    RESULTS.mkdir(parents=True, exist_ok=True)
    kinds = UNIVERSE_KINDS[args.universe]
    cache = build_cache_index(kinds)
    print(f"[universe={args.universe}] 候选代码 {len(cache)} 个")

    # --- 基准：沪深300 ---
    # 注意：生产缓存里 index_daily_000300_SH 有多份不同区间的文件，
    # 按文件大小挑会拿到只有 2019 年之后的短文件（实测 1847 行），
    # 导致 2019 年前的事件全部没有基准可比。这里按【行数】挑最长的。
    bench_path = None
    bench_rows = -1
    for directory in (CACHE_DIR, PRODUCTION_CACHE_DIR):
        if not directory.exists():
            continue
        for path in directory.glob("index_daily_000300_SH_*.csv"):
            try:
                rows = sum(1 for _ in path.open("r", encoding="utf-8-sig")) - 1
            except Exception:
                rows = 0
            if rows > bench_rows:
                bench_rows, bench_path = rows, path
    if bench_path is None:
        raise SystemExit("找不到沪深300 基准数据")
    bench = add_features(load_series(bench_path))
    bench_fwd = bench.set_index("trade_date")[[f"fwd{h}" for h in FORWARD_HORIZONS]]
    print(f"[benchmark] 沪深300 {bench_path.name} 行数 {len(bench)}")

    all_events: list[dict] = []
    fwd_tables: list[pd.DataFrame] = []
    ret5_series: list[pd.Series] = []
    used: list[str] = []
    skipped_short = 0

    for code, path in sorted(cache.items()):
        if args.exclude_broad and code in BROAD_INDEX:
            continue
        raw = load_series(path)
        if len(raw) < args.min_rows:
            skipped_short += 1
            continue
        frame = add_features(raw)
        events, fwd_table, r5 = collect_events(code, frame, args.require_trend, min_drop)
        all_events.extend(events)
        if not fwd_table.empty:
            fwd_tables.append(fwd_table)
        if not r5.empty:
            ret5_series.append(r5)
        used.append(code)

    print(f"[universe={args.universe}] 实际入池 {len(used)} 个（跳过历史过短 {skipped_short}）")

    # --- 横截面中位数基准 ---
    panel = pd.concat(fwd_tables, axis=1)
    cs_median: dict[int, dict[tuple[int, str], float]] = {}
    for h in FORWARD_HORIZONS:
        cols = [c for c in panel.columns if c.endswith(f"|fwd{h}")]
        sub = panel[cols]
        med = sub.median(axis=1, skipna=True)
        for date, value in med.items():
            if np.isfinite(value):
                cs_median.setdefault(date, {})[h] = float(value)

    # --- 市场环境：当天是不是全市场一起跌 ---
    # 用【横截面 ret5 中位数】定义，而不是"同日有几个标的触发"——
    # 后者在本采样口径下会失真（趋势中的日子本来就多个指数同时在趋势里）。
    ret5_panel = pd.concat(ret5_series, axis=1)
    cs_ret5_med = ret5_panel.median(axis=1, skipna=True)
    bench_ret5 = bench.set_index("trade_date")["ret5"]

    per_date_triggers = Counter(e["date"] for e in all_events)
    for e in all_events:
        date = e["date"]
        bm = bench_fwd.loc[date] if date in bench_fwd.index else None
        for h in FORWARD_HORIZONS:
            f = e.get(f"fwd{h}")
            if bm is not None and f is not None:
                b = bm[f"fwd{h}"]
                e[f"ex_bench{h}"] = float(f - b) if np.isfinite(b) else None
            else:
                e[f"ex_bench{h}"] = None
            cm = cs_median.get(date, {}).get(h)
            e[f"ex_cs{h}"] = float(f - cm) if (f is not None and cm is not None) else None
        e["bucket"] = bucket_of(e["z5"])
        e["same_day_triggers"] = per_date_triggers[date]
        m5 = cs_ret5_med.get(date)
        e["cs_ret5_med"] = float(m5) if m5 is not None and np.isfinite(m5) else None
        b5 = bench_ret5.get(date)
        e["mkt_ret5"] = float(b5) if b5 is not None and np.isfinite(b5) else None
        m = e["cs_ret5_med"]
        if m is None:
            e["regime"] = "unknown"
        elif m <= -0.03:
            e["regime"] = "systemic"       # 全市场一起跌（流动性/系统性）
        elif m <= -0.01:
            e["regime"] = "mixed"
        else:
            e["regime"] = "idiosyncratic"  # 市场没跌，这个行业自己被砸

    tag = args.output_tag or args.universe
    out_csv = RESULTS / f"sudden_drop_events_{tag}.csv"
    out_md = RESULTS / f"sudden_drop_summary_{tag}.md"
    pd.DataFrame(all_events).to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"[write] {out_csv}  rows={len(all_events)}")

    # ---------------- 汇总 ---------------- #
    lines: list[str] = []
    lines.append("# 急跌 vs 阴跌 —— 历史验证结果\n")
    lines.append(f"- 生成时间：{pd.Timestamp.now():%Y-%m-%d %H:%M}")
    lines.append(f"- 标的池：`{args.universe}`（{len(used)} 个代码，"
                 f"{'已剔除宽基' if args.exclude_broad else '含宽基'}）")
    lines.append(f"- 区间：{min(e['date'] for e in all_events)} ~ {max(e['date'] for e in all_events)}"
                 if all_events else "- 区间：无事件")
    lines.append(f"- 前置条件：20 交易日前收盘 > MA60"
                 + ("；60 日收益 > 0" if args.require_trend else "；不要求 60 日收益"))
    lines.append(f"- 5 日跌幅门槛：{'无' if min_drop is None else _fmt(min_drop)}")
    lines.append(f"- 事件冷却：{COOLDOWN_DAYS} 交易日；前向窗口：{', '.join(map(str, FORWARD_HORIZONS))} 交易日")
    lines.append(f"- **样本量 N = {len(all_events)}**\n")

    if not all_events:
        out_md.write_text("\n".join(lines), encoding="utf-8")
        print("[warn] 无事件")
        return

    # ---- 主表：分桶 × 期限 ---- #
    lines.append("## 1. 剂量-反应曲线（核心证据）\n")
    lines.append("> 读法：客户甲的假设成立 => 越往下的桶（跌得越急），前向收益**越好**。")
    lines.append("> 假设不成立 => 越往下的桶前向收益**越差**（跌了还会跌）。\n")

    for metric, label in (
        ("fwd", "绝对收益"),
        ("ex_bench", "超额 vs 沪深300"),
        ("ex_cs", "超额 vs 横截面中位数"),
    ):
        lines.append(f"### 1.{['fwd','ex_bench','ex_cs'].index(metric)+1} {label}\n")
        header = "| z5 桶 | N | " + " | ".join(f"{h}日中位" for h in FORWARD_HORIZONS) \
                 + " | " + " | ".join(f"{h}日胜率" for h in FORWARD_HORIZONS) + " |"
        lines.append(header)
        lines.append("|" + "---|" * (2 + 2 * len(FORWARD_HORIZONS)))
        for name, _ in Z_BUCKETS:
            sub = [e for e in all_events if e["bucket"] == name]
            if not sub:
                continue
            meds, wins = [], []
            for h in FORWARD_HORIZONS:
                s = _stats([e[f"{metric}{h}"] for e in sub])
                meds.append(_fmt(s.get("median")))
                wins.append(_fmt(s.get("win")))
            lines.append(f"| {name} | {len(sub)} | " + " | ".join(meds)
                         + " | " + " | ".join(wins) + " |")
        lines.append("")

    # ---- 对照组：急跌 vs 阴跌 ---- #
    lines.append("## 2. 急跌 vs 阴跌（直接对照）\n")
    lines.append("- **急跌组**：z5 ≤ −1.2（跌得比自身近期波动快）")
    lines.append("- **阴跌组**：z5 > −0.4，但 20 日收益 ≤ −3%（磨下来的，没有单日冲击）")
    lines.append("- **基准组**：z5 > −0.4 且 20 日收益 > −3%（没在跌的同期样本）\n")
    sharp = [e for e in all_events if e["z5"] <= -1.2]
    grind = [e for e in all_events
             if e["z5"] > -0.4 and e.get("ret20") is not None and e["ret20"] <= -0.03]
    base = [e for e in all_events
            if e["z5"] > -0.4 and (e.get("ret20") is None or e["ret20"] > -0.03)]
    lines.append(f"- 急跌 N = {len(sharp)}；阴跌 N = {len(grind)}；基准 N = {len(base)}\n")
    lines.append("| 组 | N | " + " | ".join(f"{h}日中位(绝对)" for h in FORWARD_HORIZONS)
                 + " | " + " | ".join(f"{h}日中位(超额CS)" for h in FORWARD_HORIZONS)
                 + " | 20日最坏回撤中位 | 20日往返中位 |")
    lines.append("|" + "---|" * (3 + 3 * len(FORWARD_HORIZONS)))
    for label, group in (("急跌 z5≤−1.2", sharp),
                         ("阴跌 z5>−0.4 & ret20≤−3%", grind),
                         ("基准 没在跌", base)):
        if not group:
            continue
        ab = [_fmt(_stats([e[f"fwd{h}"] for e in group]).get("median")) for h in FORWARD_HORIZONS]
        cs = [_fmt(_stats([e[f"ex_cs{h}"] for e in group]).get("median")) for h in FORWARD_HORIZONS]
        mae = _fmt(_stats([e["mae20"] for e in group]).get("median"))
        rnd = _fmt(_stats([e["round20"] for e in group]).get("median"))
        lines.append(f"| {label} | {len(group)} | " + " | ".join(ab)
                     + " | " + " | ".join(cs) + f" | {mae} | {rnd} |")
    lines.append("")
    lines.append("> `20日往返` = 从暴跌前一日收盘（t−5）到 t+20 的完整往返收益，"
                 "衡量「砸下去之后有没有回到原位」。\n")

    # ---- 显著性：按日期聚类的 bootstrap ---- #
    lines.append("### 2.1 差异是否显著（按日期整块重抽 bootstrap，2000 次）\n")
    lines.append("> 事件在同一天上高度相关，逐事件重抽会把显著性夸大好几倍，所以按【日期】整块重抽。")
    lines.append("> 括号内为 5%~95% 置信区间；**区间跨过 0 => 两组没有可区分的差异**。\n")
    lines.append("| 对比 | 指标 | 急跌中位 − 对照中位 | 90% CI |")
    lines.append("|---|---|---|---|")
    for label, ref in (("急跌 vs 基准(没在跌)", base), ("急跌 vs 阴跌", grind)):
        for h in (20, 60):
            for metric, mname in ((f"ex_cs{h}", f"{h}日超额CS"), (f"fwd{h}", f"{h}日绝对")):
                mean_d, lo, hi = clustered_bootstrap_median_diff(sharp, ref, metric)
                if not np.isfinite(mean_d):
                    lines.append(f"| {label} | {mname} | 样本不足 | — |")
                    continue
                cross = "（跨0，不显著）" if lo <= 0 <= hi else ""
                lines.append(f"| {label} | {mname} | {_fmt(mean_d)} | "
                             f"[{_fmt(lo)}, {_fmt(hi)}] {cross} |")
    lines.append("")

    # ---- 关键分层：市场跌 vs 行业自己被砸 ---- #
    lines.append("## 3. 关键分层：全市场一起跌，还是这个行业自己被砸\n")
    lines.append("> 用**横截面 ret5 中位数**判定当天市场状态：")
    lines.append("> `systemic` = 全市场中位数 5 日跌 ≥3%（流动性/系统性冲击）")
    lines.append("> `idiosyncratic` = 全市场中位数 5 日基本没跌，是这个行业单独被砸（消息/抽血）\n")
    lines.append("| 市场环境 | 组 | N | 20日绝对中位 | 60日绝对中位 | 20日超额CS中位 | 60日超额CS中位 | 20日往返中位 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for regime in ("idiosyncratic", "mixed", "systemic"):
        for label, pred in (("急跌 z5≤−1.2", lambda e: e["z5"] <= -1.2),
                            ("其他", lambda e: e["z5"] > -1.2)):
            sub = [e for e in all_events if e["regime"] == regime and pred(e)]
            if len(sub) < 20:
                continue
            f20 = _fmt(_stats([e["fwd20"] for e in sub]).get("median"))
            f60 = _fmt(_stats([e["fwd60"] for e in sub]).get("median"))
            c20 = _fmt(_stats([e["ex_cs20"] for e in sub]).get("median"))
            c60 = _fmt(_stats([e["ex_cs60"] for e in sub]).get("median"))
            r20 = _fmt(_stats([e["round20"] for e in sub]).get("median"))
            lines.append(f"| {regime} | {label} | {len(sub)} | {f20} | {f60} | {c20} | {c60} | {r20} |")
    lines.append("")

    # ---- 分层：急跌后有没有守住 MA60 ---- #
    lines.append("## 4. 分层：急跌后趋势有没有破\n")
    lines.append("> 「急跌但还站在 MA60 上」= 洗盘；「急跌且已跌破 MA60」= 趋势破了。\n")
    lines.append("| 组 | N | 20日绝对中位 | 60日绝对中位 | 20日超额CS中位 | 60日超额CS中位 | 20日往返中位 |")
    lines.append("|---|---|---|---|---|---|---|")
    for label, pred in (
        ("急跌 + 仍站上MA60", lambda e: e["z5"] <= -1.2 and e.get("above_ma60_now") is True),
        ("急跌 + 已跌破MA60", lambda e: e["z5"] <= -1.2 and e.get("above_ma60_now") is False),
        ("急跌 + 距60日高点<5%", lambda e: e["z5"] <= -1.2
         and e.get("dd_from_high60") is not None and e["dd_from_high60"] > -0.05),
        ("急跌 + 距60日高点>10%", lambda e: e["z5"] <= -1.2
         and e.get("dd_from_high60") is not None and e["dd_from_high60"] <= -0.10),
    ):
        sub = [e for e in all_events if pred(e)]
        if len(sub) < 20:
            continue
        f20 = _fmt(_stats([e["fwd20"] for e in sub]).get("median"))
        f60 = _fmt(_stats([e["fwd60"] for e in sub]).get("median"))
        c20 = _fmt(_stats([e["ex_cs20"] for e in sub]).get("median"))
        c60 = _fmt(_stats([e["ex_cs60"] for e in sub]).get("median"))
        r20 = _fmt(_stats([e["round20"] for e in sub]).get("median"))
        lines.append(f"| {label} | {len(sub)} | {f20} | {f60} | {c20} | {c60} | {r20} |")
    lines.append("")

    # ---- 年份分布 ---- #
    lines.append("## 5. 事件年份分布\n")
    by_year = Counter(e["date"][:4] for e in all_events)
    lines.append("| 年份 | 事件数 | 其中急跌(z5≤−1.2) | 急跌20日超额CS中位 |")
    lines.append("|---|---|---|---|")
    for year in sorted(by_year):
        sub = [e for e in all_events if e["date"][:4] == year]
        sh = [e for e in sub if e["z5"] <= -1.2]
        med = _stats([e["ex_cs20"] for e in sh]).get("median")
        lines.append(f"| {year} | {len(sub)} | {len(sh)} | {_fmt(med)} |")
    lines.append("")

    # ---- 极端桶的逐事件明细（前 20）---- #
    lines.append("## 6. 最急跌桶样本明细（z5 ≤ −1.5，按 z5 升序前 30）\n")
    lines.append("| 代码 | 日期 | z5 | 5日跌幅 | 距60日高点 | 20日绝对 | 60日绝对 | 20日超额CS | 20日最坏 |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    extreme = sorted([e for e in all_events if e["z5"] <= -1.5], key=lambda e: e["z5"])[:30]
    for e in extreme:
        lines.append(
            f"| {e['code']} | {e['date']} | {e['z5']:.2f} | {_fmt(e['ret5'])} | "
            f"{_fmt(e['dd_from_high60'])} | {_fmt(e['fwd20'])} | {_fmt(e['fwd60'])} | "
            f"{_fmt(e['ex_cs20'])} | {_fmt(e['mae20'])} |"
        )
    lines.append("")

    # ---- 结论区（占位，由人工填写）---- #
    lines.append("## 7. 结论（脚本不自动下结论）\n")
    lines.append("- 是否单调：见 §1 各桶中位数走向")
    lines.append("- 急跌是否优于阴跌：见 §2 + §2.1 显著性")
    lines.append("- 是否只在特定市场环境成立：见 §3")
    lines.append("- 是否只在趋势未破时成立：见 §4")
    lines.append("- 分年稳定性：见 §5")
    lines.append("- **脚本不判断「值不值得做」，只给出可复算的数字。**\n")

    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"[write] {out_md}")
    print(f"[done] 事件 {len(all_events)}，急跌 {len(sharp)}，阴跌 {len(grind)}")


if __name__ == "__main__":
    main()

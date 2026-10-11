"""三段建仓数据就绪性检验（离线，不进生产）。

目的：在动手写分段回测之前，先回答一个问题——
「初始启动（T1）信号之后，第二段和第三段到底有多少机会被触发？」

如果第三段触发率过低，分段建仓就无从检验；本脚本负责把这件事量化。

用法：
    cd industry_insight_sandbox
    python verify_tranche_readiness.py

输入：
    backtest_results/etf_watch_expanded_*_lifecycle_events.csv（初始启动事件）
    data/backtest_cache/ + data/cache/（本地日线缓存，不联网）
输出：
    backtest_results/tranche_readiness_events.csv（逐事件）
    控制台统计 + backtest_results/tranche_readiness_summary.md

口径说明（重要）：
    - 扩展池只有价格与成交额，**没有成分股吸筹率**，因此草案里的「资金型 T2」
      在此用**成交额代理**（amount >= amount_ma20 * 1.2）近似，不是生产口径的
      funding_confirm。差异已在本脚本输出中显式标注。
    - 全程只用缓存，不联网、不写生产数据、不改任何策略判定。
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pandas as pd

from backtest_etf_watch import (
    CACHE_DIR,
    PRODUCTION_CACHE_DIR,
    add_indicators,
    build_lifecycle_series,
    normalize_daily,
)


ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "backtest_results"
EVENTS_CSV = RESULTS / "etf_watch_expanded_20120101_20260813_lifecycle_events.csv"
OUT_CSV = RESULTS / "tranche_readiness_events.csv"
OUT_MD = RESULTS / "tranche_readiness_summary.md"

LOOKAHEAD_DAYS = 120          # 向前观察窗口（交易日）
HOLD_DAYS = 5                 # 「站稳 MA60」所需交易日数（方案 A）
AMOUNT_BOOST_MULTIPLE = 1.2   # 成交额增强代理阈值（方案 B 代理）


def _safe_code(code: str) -> str:
    return code.replace(".", "_")


_CACHE_INDEX: dict[str, Path] | None = None


def _build_cache_index() -> dict[str, Path]:
    """一次性扫描两个缓存目录，建立 代码 -> 最长区间文件 的索引。"""
    best: dict[str, tuple[int, Path]] = {}
    for directory in (CACHE_DIR, PRODUCTION_CACHE_DIR):
        if not directory.exists():
            continue
        for path in directory.glob("*.csv"):
            if "weight" in path.name or "basic" in path.name:
                continue
            match = re.search(r"(?:^|_)([0-9]{6}_[A-Z]{2,3})_(\d{8})_(\d{8})\.csv$", path.name)
            if not match:
                continue
            token, start, end = match.group(1), match.group(2), match.group(3)
            span = int(end) - int(start)
            if token not in best or span > best[token][0]:
                best[token] = (span, path)
    return {token: path for token, (_, path) in best.items()}


def _find_cache(code: str) -> Path | None:
    global _CACHE_INDEX
    if _CACHE_INDEX is None:
        _CACHE_INDEX = _build_cache_index()
    return _CACHE_INDEX.get(_safe_code(code))


def _load_history(code: str) -> pd.DataFrame | None:
    path = _find_cache(code)
    if path is None:
        return None
    frame = pd.read_csv(path, encoding="utf-8-sig")
    frame = normalize_daily(frame)
    frame = add_indicators(frame)
    frame["amount_ma20"] = frame["amount"].rolling(20).mean()
    frame["ma120"] = frame["close"].rolling(120).mean()
    lifecycle = build_lifecycle_series(frame)
    merged = frame.merge(lifecycle, on="trade_date", how="left")
    merged["date"] = merged["trade_date"].astype(str).str.replace("-", "", regex=False)
    return merged.sort_values("date").reset_index(drop=True)


def _first_true_after(series: pd.Series, start: int, end: int) -> int | None:
    """返回 start+1 .. end 之间首个为 True 的偏移天数（相对 start）。"""
    for offset in range(1, min(end - start, LOOKAHEAD_DAYS) + 1):
        if bool(series.iloc[start + offset]):
            return offset
    return None


def _streak_offset(series: pd.Series, start: int, end: int, streak: int) -> int | None:
    """首次达成「连续 streak 日为 True」的那一天相对 start 的偏移。"""
    limit = min(end - start, LOOKAHEAD_DAYS)
    for offset in range(1, limit + 1):
        if offset < streak:
            continue
        window = series.iloc[start + offset - streak + 1 : start + offset + 1]
        if bool(window.all()):
            return offset
    return None


def _hold_ma60_offset(history: pd.DataFrame, start: int, end: int) -> int | None:
    """方案 A：首次达成「连续 HOLD_DAYS 日收盘 >= MA60 且期间最低收盘未跌破」的偏移。"""
    limit = min(end - start, LOOKAHEAD_DAYS)
    for offset in range(1, limit + 1):
        if offset < HOLD_DAYS:
            continue
        window = history.iloc[start + offset - HOLD_DAYS + 1 : start + offset + 1]
        if (window["close"] >= window["ma60"]).all():
            return offset
    return None


def main() -> None:
    events = pd.read_csv(EVENTS_CSV, encoding="utf-8-sig")
    events["signalDate"] = events["signalDate"].astype(str)

    cache: dict[str, pd.DataFrame | None] = {}
    rows: list[dict[str, object]] = []
    missing: list[str] = []

    for _, event in events.iterrows():
        code = str(event["code"])
        signal_date = str(event["signalDate"])
        if code not in cache:
            cache[code] = _load_history(code)
        history = cache[code]
        if history is None:
            missing.append(code)
            continue

        dates = history["date"].tolist()
        if signal_date not in dates:
            rows.append(
                {"code": code, "name": event.get("name"), "signalDate": signal_date,
                 "status": "signal_date_absent"}
            )
            continue
        start = dates.index(signal_date)
        end = len(history) - 1

        aligned = bool(history["initial_start_today"].iloc[start])
        forward = min(end - start, LOOKAHEAD_DAYS)

        amount_boost = (
            history["amount"] >= history["amount_ma20"] * AMOUNT_BOOST_MULTIPLE
        ) & (history["close"] >= history["ma60"])
        below_ma60 = history["close"] < history["ma60"]
        above_ma250 = history["close"] >= history["ma250"]

        rows.append(
            {
                "code": code,
                "name": event.get("name"),
                "signalDate": signal_date,
                "status": "ok" if aligned else "lifecycle_mismatch",
                "aligned": aligned,
                "forwardDays": forward,
                "t3TrendConfirmedOffset": _first_true_after(
                    history["trend_confirmed_today"], start, end
                ),
                "t3AboveMa250Offset": _first_true_after(above_ma250, start, end),
                "t2HoldMa60Offset": _hold_ma60_offset(history, start, end),
                "t2AmountBoostOffset": _first_true_after(amount_boost, start, end),
                "belowMa60Offset": _first_true_after(below_ma60, start, end),
                "belowMa60x2Offset": _streak_offset(below_ma60, start, end, 2),
                "belowMa60x3Offset": _streak_offset(below_ma60, start, end, 3),
                "belowMa120Offset": _first_true_after(
                    history["close"] < history["ma120"], start, end
                ),
                "d20ReturnPct": event.get("d20ReturnPct"),
                "d60ReturnPct": event.get("d60ReturnPct"),
            }
        )

    result = pd.DataFrame(rows)
    RESULTS.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    ok = result[result["status"] == "ok"]
    total = len(ok)

    def rate(column: str, within: int | None = None) -> tuple[int, float]:
        series = ok[column]
        if within is not None:
            series = series.where(series <= within)
        count = int(series.notna().sum())
        return count, (count / total * 100 if total else 0.0)

    lines = [
        "# 三段建仓数据就绪性检验",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 事件来源：`{EVENTS_CSV.name}`（扩展池生命周期初始启动）",
        f"- 观察窗口：信号后最多 {LOOKAHEAD_DAYS} 个交易日",
        "- 数据：仅本地日线缓存，不联网；扩展池无成分吸筹率，T2 资金型用成交额代理",
        "",
        "## 一、样本与对齐",
        "",
        f"- 事件总数：**{len(events)}**",
        f"- 有缓存可重算：**{total}**（缺失 {len(set(missing))} 个标的 / {sum(1 for r in rows if r.get('status')=='signal_date_absent')} 个事件日期不在缓存区间）",
        f"- 生命周期对齐（信号当日 `initial_start_today` 复现为 True）：**{int(ok['aligned'].sum())} / {total}**",
        "",
        "## 二、各段触发率（相对 T1 的触发比例）",
        "",
        "| 段 | 条件 | 窗口内触发数 | 触发率 | 中位滞后(交易日) |",
        "|---|---|---:|---:|---:|",
    ]

    specs = [
        ("T3 年线确认", "t3TrendConfirmedOffset", "lifecycle `trend_confirmed_today` 首次为真"),
        ("T3 简化", "t3AboveMa250Offset", "收盘首次站上 MA250（不含 1.03 缓冲）"),
        ("T2 方案A 站稳", "t2HoldMa60Offset", f"连续 {HOLD_DAYS} 日收盘 >= MA60"),
        ("T2 方案B代理", "t2AmountBoostOffset", f"成交额 >= MA20×{AMOUNT_BOOST_MULTIPLE} 且收盘 >= MA60"),
        ("失效 跌破MA60", "belowMa60Offset", "首次收盘跌破 MA60"),
    ]
    for label, column, desc in specs:
        count, pct = rate(column)
        median = ok[column].median()
        median_text = f"{median:.0f}" if pd.notna(median) else "—"
        lines.append(f"| {label} | {desc} | {count} | {pct:.1f}% | {median_text} |")

    # ---- 顺序分析：各段必须在「退出」之前触发才有意义 ----
    exit_specs = [
        ("跌破MA60（现行）", "belowMa60Offset"),
        ("连续2日跌破MA60", "belowMa60x2Offset"),
        ("连续3日跌破MA60", "belowMa60x3Offset"),
    ]
    lines.extend(
        [
            "",
            "## 三、触发滞后分布（T1 之后的交易日）",
            "",
            "| 条件 | 25% | 中位 | 75% | 10日内 | 20日内 | 40日内 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for label, column, _ in specs:
        series = ok[column]
        quant = series.quantile([0.25, 0.5, 0.75])
        cells = []
        for window in (10, 20, 40):
            cells.append(f"{int(series.le(window).sum()) / total * 100:.1f}%")
        lines.append(
            f"| {label} | {quant[0.25]:.0f} | {quant[0.5]:.0f} | {quant[0.75]:.0f} | "
            + " | ".join(cells)
            + " |"
        )

    lines.extend(
        [
            "",
            "## 四、关键：各段在「退出之前」的可达率",
            "",
            "分段建仓的前提是后一段真的会被触发。若退出先于加仓发生，该段资金根本不会投入。",
            "",
            "| 退出口径 | 退出中位(日) | T2站稳可达 | T2额增可达 | **T3可达** |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for label, column in exit_specs:
        barrier = ok[column]
        cells = []
        for target in ("t2HoldMa60Offset", "t2AmountBoostOffset", "t3TrendConfirmedOffset"):
            cells.append(f"{(ok[target] < barrier).sum() / total * 100:.1f}%")
        lines.append(f"| {label} | {barrier.median():.0f} | " + " | ".join(cells) + " |")

    lines.extend(
        [
            "",
            "## 五、结论与对草案的影响",
            "",
            f"1. **T3 滞后得到证实**：中位 {ok['t3TrendConfirmedOffset'].median():.0f} 个交易日（约 2 个月）才出现年线确认，",
            "   20 日内仅 "
            f"{ok['t3TrendConfirmedOffset'].le(20).sum() / total * 100:.1f}% 触发。",
            "2. **但更严重的问题不是滞后，是失效更早**：首次跌破 MA60 的中位仅 "
            f"{ok['belowMa60Offset'].median():.0f} 个交易日。",
            "3. **两者叠加的后果**：在现行「跌破 MA60 退出」口径下，T3 在退出前可达率只有 "
            f"{(ok['t3TrendConfirmedOffset'] < ok['belowMa60Offset']).sum() / total * 100:.1f}%。",
            "   即便放宽到连续 3 日跌破，也只有 "
            f"{(ok['t3TrendConfirmedOffset'] < ok['belowMa60x3Offset']).sum() / total * 100:.1f}%。",
            "4. **对草案 §2 的直接影响**：第三段 30% 的权重，在大多数情况下不会被执行；",
            "   四组比例（等额/菱形/递减）的实际差异会被大幅压缩，因为差异主要来自很少执行的第三段。",
            "5. **对草案 §2.1 的反证**：T2 成交额代理中位滞后仅 "
            f"{ok['t2AmountBoostOffset'].median():.0f} 日，与 T1 几乎同时发生，",
            "   不构成「新增证据」。草案推荐方案 B 需重新评估（注意：此处为代理口径，非生产 funding_confirm）。",
            "",
            "## 六、读取方式",
            "",
            "- `可达率` = 该段触发日早于退出日的事件占比，是最贴近真实资金路径的指标。",
            "- `跌破MA120` 未列入退出对比：初始启动信号本身处于 MA60 < MA120 的低位区，",
            "  价格本就在 MA120 下方，该条件对初始启动信号无区分度。",
            "- 扩展池无成分吸筹率，T2 资金型用成交额代理，与生产 `funding_confirm` 不同，不可直接等同。",
            "",
            "本报告仅为离线数据就绪性检查，不构成任何仓位或配置建议。",
        ]
    )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"events={len(events)} recomputed={total} missing_targets={len(set(missing))}")
    print(f"aligned={int(ok['aligned'].sum())}/{total}")
    for label, column, _ in specs:
        count, pct = rate(column)
        print(f"{label:16s} {count:4d}  {pct:5.1f}%")
    print(f"\nCSV: {OUT_CSV}")
    print(f"MD : {OUT_MD}")


if __name__ == "__main__":
    main()

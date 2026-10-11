"""急跌读数参考实现（观察层 · 候选规格 v1）。

纯函数，**无副作用**：不读文件、不写文件、不依赖项目内其他模块、
不做网络请求。可被 generate 类脚本直接 import。

对应规格：`急跌读数-规格-v1.md`

⚠️ 三不：不含买卖含义、不做底部确认、不输出任何判断位。
"""

from __future__ import annotations

import math
from statistics import mean, pstdev
from typing import Sequence

SCHEMA_VERSION = "1.0"
WINDOW_DAYS = 20
THRESHOLD_PCT = -10.0
EPS = 1e-9  # 百分数比较容差，用于「阈值含等于」的判断
NOTE = (
    "纯几何读数：描述过去 20 个交易日内从最高收盘到当前的回撤结构与跌法，"
    "不含买卖含义。"
)


def _safe_div(a: float, b: float) -> float | None:
    if b in (0, None) or a is None or (isinstance(b, float) and b == 0):
        return None
    try:
        r = a / b
    except (TypeError, ZeroDivisionError):
        return None
    return None if (isinstance(r, float) and (math.isnan(r) or math.isinf(r))) else r


def _pct(new: float, old: float) -> float | None:
    r = _safe_div(new, old)
    return None if r is None else (r - 1) * 100


def _max_consecutive_down(closes: Sequence[float]) -> int:
    """按收盘价计算最大连跌天数。"""
    best = cur = 0
    for i in range(1, len(closes)):
        if closes[i] < closes[i - 1]:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def compute_drawdown(
    dates: Sequence[str],
    closes: Sequence[float],
    volumes: Sequence[float] | None = None,
    bench_dates: Sequence[str] | None = None,
    bench_closes: Sequence[float] | None = None,
    *,
    window: int = WINDOW_DAYS,
    threshold_pct: float = THRESHOLD_PCT,
    ma_windows: Sequence[int] = (20, 60),
) -> dict:
    """计算截至序列最后一根 K 线的急跌读数。

    Args:
        dates/closes: **升序**（早→晚）的日期与收盘价，最后一根即 asOf。
        volumes: 可选，升序成交量；缺失则 volumeRatio 为 None。
        bench_dates/bench_closes: 可选基准（沪深300）序列，用于同期市场涨跌。
        window: 回撤窗口（交易日）。
        threshold_pct: 触发阈值（负的百分数）。
        ma_windows: 需要输出的均线窗口。

    Returns:
        规格 §4 的字段字典（键名与规格完全一致）。
    """
    n = len(closes)
    assert n == len(dates), "dates 与 closes 长度必须一致"

    out: dict = {
        "schemaVersion": SCHEMA_VERSION,
        "asOf": str(dates[-1]) if n else None,
        "triggered": False,
        "windowDays": 0,
        "thresholdPct": threshold_pct,
        "drawdownPct": None,
        "peakDate": None,
        "peakClose": None,
        "drawdownDays": 0,
        "maxSingleDayDropPct": None,
        "downDaysOver2Pct": 0,
        "downDaysOver3Pct": 0,
        "upDaysRatio": None,
        "maxConsecutiveDownDays": 0,
        "volumeRatio": None,
        "volatilityRatio": None,
        "ma20GapPct": None,
        "ma60GapPct": None,
        "marketRetPct": None,
        "excessPct": None,
        "decisionUse": False,
        "note": NOTE,
    }

    if n < 2:
        return out

    # —— 1. 窗口截取 ——
    lo = max(0, n - window)
    w_dates = list(dates[lo:])
    w_closes = list(closes[lo:])
    w_vol = list(volumes[lo:]) if volumes is not None and len(volumes) == n else None
    out["windowDays"] = len(w_closes)

    # —— 2. 峰值（并列取最早 -> argmax 天然满足）——
    peak_rel = max(range(len(w_closes)), key=lambda i: w_closes[i])
    peak_close = w_closes[peak_rel]
    peak_date = w_dates[peak_rel]
    cur_close = w_closes[-1]
    out["peakDate"] = str(peak_date)
    out["peakClose"] = round(peak_close, 4)

    dd = _pct(cur_close, peak_close)
    out["drawdownPct"] = None if dd is None else round(dd, 2)
    # ⚠️ 规格是「阈值**含等于**」。直接写 `dd <= threshold_pct` 会被浮点精度坑：
    #    9.0/10.0-1 == -0.09999999999999998，-10% 边界会被判成 False。
    #    故留 1e-9 容差（远小于百分数的有效位数，不会误纳真实差异）。
    out["triggered"] = bool(dd is not None and dd <= threshold_pct + EPS)

    # drawdownDays：峰值日 -> 当前日 的交易日个数（不含起点、含终点）
    out["drawdownDays"] = len(w_closes) - 1 - peak_rel

    # —— 3. 跌法：区间 = [peak ... current] ——
    seg = w_closes[peak_rel:]
    if len(seg) >= 2:
        rets = [(seg[i] / seg[i - 1] - 1) * 100 for i in range(1, len(seg)) if seg[i - 1]]
        if rets:
            out["maxSingleDayDropPct"] = round(min(rets), 2)
            out["downDaysOver2Pct"] = sum(1 for r in rets if r <= -2)
            out["downDaysOver3Pct"] = sum(1 for r in rets if r <= -3)
            out["upDaysRatio"] = round(sum(1 for r in rets if r > 0) / len(rets), 2)
        out["maxConsecutiveDownDays"] = _max_consecutive_down(seg)

    # —— 4. 量能与波动：对比峰值日之前的 20 根 ——
    pre_lo = max(0, lo + peak_rel - 20)
    pre_hi = lo + peak_rel
    pre_closes = list(closes[pre_lo:pre_hi])
    if w_vol and sum(v for v in w_vol if v) > 0:
        pre_vol = list(volumes[pre_lo:pre_hi]) if volumes is not None else []
        base_v = mean([v for v in pre_vol if v]) if pre_vol else None
        seg_vol = w_vol[peak_rel:]
        cur_v = mean([v for v in seg_vol if v]) if seg_vol else None
        if base_v and cur_v:
            out["volumeRatio"] = round(cur_v / base_v, 2)
    pre_rets = [
        (pre_closes[i] / pre_closes[i - 1] - 1) * 100
        for i in range(1, len(pre_closes))
        if pre_closes[i - 1]
    ]
    if len(pre_rets) > 1 and len(seg) >= 3:
        seg_rets = [(seg[i] / seg[i - 1] - 1) * 100 for i in range(1, len(seg)) if seg[i - 1]]
        base_std = pstdev(pre_rets)
        cur_std = pstdev(seg_rets) if len(seg_rets) > 1 else None
        if base_std and cur_std:
            out["volatilityRatio"] = round(cur_std / base_std, 2)

    # —— 5. 均线位置 ——
    for mw in ma_windows:
        key = f"ma{mw}GapPct"
        if key not in out:
            continue
        if n >= mw:
            ma = mean(closes[-mw:])
            gap = _pct(cur_close, ma)
            out[key] = None if gap is None else round(gap, 2)

    # —— 6. 同期基准 ——
    if bench_dates and bench_closes and len(bench_dates) == len(bench_closes):
        bd = list(bench_dates)
        bc = list(bench_closes)
        asof_date = str(dates[-1])
        # 起点：>= peak_date 的第一根基准 K 线
        pk = next((i for i, d in enumerate(bd) if str(d) >= str(peak_date)), None)
        # 终点：<= asOf 的**最后一根**基准 K 线。
        # ⚠️ 不能直接取 len(bd)-1：基准序列通常比目标序列长，
        #    那样会把区间终点算到基准的最后一天，导致 marketRetPct 错位。
        cu = None
        for i, d in enumerate(bd):
            if str(d) <= asof_date:
                cu = i
            else:
                break
        if pk is not None and cu is not None and pk <= cu and bc[pk] and bc[cu]:
            mr = _pct(bc[cu], bc[pk])
            out["marketRetPct"] = None if mr is None else round(mr, 2)
            if mr is not None and dd is not None:
                out["excessPct"] = round(dd - mr, 2)

    return out

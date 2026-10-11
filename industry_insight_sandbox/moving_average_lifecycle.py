from __future__ import annotations

from typing import Any

import pandas as pd


SEPARATION_LOOKBACK_DAYS = 500
SEPARATION_MIN_OBSERVATIONS = 120
SEPARATION_RANK_THRESHOLD = 0.70
SEPARATION_MIN_DISTANCE = 0.05
CONVERGENCE_LOOKBACK_DAYS = 30
CONVERGENCE_REQUIRED_DAYS = 20
WARM_UP_LOOKBACK_DAYS = 20


def _ma_stack_code(latest: Any) -> str:
    """均线排列顺序码 —— 纯几何事实，可由三条均线直接复算。

    例：MA20>MA60>MA250 表示短期均线在上、长期均线在下。
    任一条均线缺失时对应段记为 --，不给出任何方向性解读。
    """
    try:
        ma20 = float(latest["ma20"])
        ma60 = float(latest["ma60"])
        ma250 = float(latest["ma250"])
    except (KeyError, TypeError, ValueError):
        return "MA--"
    import pandas as _pd

    if any(_pd.isna(v) for v in (ma20, ma60, ma250)):
        parts = [
            name
            for name, value in (("MA20", ma20), ("MA60", ma60), ("MA250", ma250))
            if not _pd.isna(value)
        ]
        return ">".join(parts) if parts else "MA--"
    order = sorted(
        (("MA20", ma20), ("MA60", ma60), ("MA250", ma250)),
        key=lambda item: item[1],
        reverse=True,
    )
    return ">".join(name for name, _ in order)


def _compact_date(value: Any) -> str:
    return str(value).replace("-", "")[:8]


def _as_percent(value: float | None) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value) * 100, 4)


def _crossed_up(previous: pd.Series, current: pd.Series, column: str) -> bool:
    values = [
        previous.get("close"),
        previous.get(column),
        current.get("close"),
        current.get(column),
    ]
    return bool(
        not any(pd.isna(value) for value in values)
        and float(previous["close"]) < float(previous[column])
        and float(current["close"]) >= float(current[column])
    )


def _death_cross(previous: pd.Series, current: pd.Series) -> bool:
    values = [
        previous.get("ma60"),
        previous.get("ma250"),
        current.get("ma60"),
        current.get("ma250"),
    ]
    return bool(
        not any(pd.isna(value) for value in values)
        and float(previous["ma60"]) >= float(previous["ma250"])
        and float(current["ma60"]) < float(current["ma250"])
    )


def _separation_at(daily: pd.DataFrame, index: int) -> dict[str, Any]:
    row = daily.iloc[index]
    ma60 = row.get("ma60")
    ma250 = row.get("ma250")
    if (
        pd.isna(ma60)
        or pd.isna(ma250)
        or float(ma250) == 0
        or float(ma60) >= float(ma250)
    ):
        return {
            "separation": None,
            "rank": None,
            "threshold": None,
            "observations": 0,
            "passed": False,
        }

    current = (float(ma250) - float(ma60)) / float(ma250)
    start = max(0, index - SEPARATION_LOOKBACK_DAYS)
    history = daily.iloc[start:index].copy()
    history = history[
        history["ma60"].notna()
        & history["ma250"].notna()
        & (history["ma250"] != 0)
        & (history["ma60"] < history["ma250"])
    ]
    separations = (
        (history["ma250"] - history["ma60"]) / history["ma250"]
    ).dropna()
    observations = len(separations)
    if observations < SEPARATION_MIN_OBSERVATIONS:
        return {
            "separation": current,
            "rank": None,
            "threshold": None,
            "observations": observations,
            "passed": False,
        }

    threshold = float(separations.quantile(SEPARATION_RANK_THRESHOLD))
    rank = float((separations <= current).mean())
    return {
        "separation": current,
        "rank": rank,
        "threshold": threshold,
        "observations": observations,
        "passed": bool(
            current >= SEPARATION_MIN_DISTANCE
            and rank >= SEPARATION_RANK_THRESHOLD
        ),
    }


def _convergence_days_before(daily: pd.DataFrame, index: int) -> int:
    window = daily.iloc[max(0, index - CONVERGENCE_LOOKBACK_DAYS):index]
    ordered = (
        window["close"].notna()
        & window["ma20"].notna()
        & window["ma60"].notna()
        & (window["close"] < window["ma20"])
        & (window["ma20"] < window["ma60"])
    )
    return int(ordered.sum())


def _latest_cross_before(
    crosses: list[int],
    index: int,
    lookback: int,
) -> int | None:
    candidates = [
        cross_index
        for cross_index in crosses
        if max(1, index - lookback) <= cross_index < index
    ]
    return candidates[-1] if candidates else None


def evaluate_moving_average_lifecycle(daily: pd.DataFrame) -> dict[str, Any]:
    required = {"trade_date", "close", "ma20", "ma60", "ma250"}
    missing = sorted(required.difference(daily.columns))
    if missing:
        raise ValueError(
            f"Moving-average lifecycle is missing columns: {', '.join(missing)}"
        )
    if daily.empty:
        raise ValueError("Moving-average lifecycle requires non-empty daily data.")

    frame = (
        daily[list(required)]
        .copy()
        .sort_values("trade_date")
        .reset_index(drop=True)
    )
    ma20_crosses: list[int] = []
    ma60_crosses: list[int] = []
    ma250_crosses: list[int] = []
    death_crosses: list[int] = []
    for index in range(1, len(frame)):
        previous = frame.iloc[index - 1]
        current = frame.iloc[index]
        if _crossed_up(previous, current, "ma20"):
            ma20_crosses.append(index)
        if _crossed_up(previous, current, "ma60"):
            ma60_crosses.append(index)
        if _crossed_up(previous, current, "ma250"):
            ma250_crosses.append(index)
        if _death_cross(previous, current):
            death_crosses.append(index)

    initial_events: list[dict[str, Any]] = []
    for index in ma60_crosses:
        death_candidates = [
            death_index
            for death_index in death_crosses
            if max(1, index - SEPARATION_LOOKBACK_DAYS)
            <= death_index
            < index
        ]
        warm_up_index = _latest_cross_before(
            ma20_crosses,
            index,
            WARM_UP_LOOKBACK_DAYS,
        )
        convergence_days = _convergence_days_before(frame, index)
        safety = _separation_at(frame, index)
        if (
            death_candidates
            and warm_up_index is not None
            and convergence_days >= CONVERGENCE_REQUIRED_DAYS
            and safety["passed"]
        ):
            initial_events.append(
                {
                    "index": index,
                    "deathCrossIndex": death_candidates[-1],
                    "warmUpIndex": warm_up_index,
                    "convergenceDays": convergence_days,
                    "safety": safety,
                }
            )

    latest_index = len(frame) - 1
    current_safety = _separation_at(frame, latest_index)
    current_convergence_days = _convergence_days_before(frame, len(frame))
    current_warm_up_index = _latest_cross_before(
        ma20_crosses,
        len(frame),
        WARM_UP_LOOKBACK_DAYS,
    )
    initial_event = initial_events[-1] if initial_events else None
    trend_index = None
    if initial_event is not None:
        later_trend_crosses = [
            index
            for index in ma250_crosses
            if index >= initial_event["index"]
        ]
        trend_index = later_trend_crosses[-1] if later_trend_crosses else None

    latest = frame.iloc[-1]
    above_ma20 = bool(
        pd.notna(latest["ma20"]) and latest["close"] >= latest["ma20"]
    )
    above_ma60 = bool(
        pd.notna(latest["ma60"]) and latest["close"] >= latest["ma60"]
    )
    above_ma250 = bool(
        pd.notna(latest["ma250"]) and latest["close"] >= latest["ma250"]
    )
    trend_confirmed_active = bool(trend_index is not None and above_ma250)
    initial_start_active = bool(
        initial_event is not None
        and not trend_confirmed_active
        and above_ma60
    )
    warm_up_active = bool(
        current_warm_up_index is not None
        and current_safety["passed"]
        and above_ma20
    )

    # 观察层只输出【几何位置】，不输出任何资格/建议判断。
    # 原 label（年线趋势确认 / 初始启动 / 短线转暖 / 低位收敛 / 未形成）与
    # capitalInterface（scale_in_eligible 等）均含主动含义，已移除。
    #
    # stateCode 是纯几何：只看【最新收盘价落在哪条均线之上】，
    # 与 aboveMa20 / aboveMa60 / aboveMa250 三个布尔量严格一致，
    # 任何人拿收盘价 + 均线值都能一行复算。
    #
    # ⚠️ 不要拿「有没有发生过上穿事件」来门控 stateCode：
    # 事件门控会让「站在全部均线之上、但近期没有上穿记录」的标的
    # 掉进 below_ma20，页面就会出现「MA20 下方 + 距MA250 +6%」的自相矛盾
    # （2026-09-19 实测：25 个标的里多数踩这个坑）。
    # 事件语义（是否刚上穿、是否失效）保留在 stateAboveMa60 / stateAboveMa250 /
    # ma60CrossUpInvalidated，由执行层自行解读。
    if above_ma250:
        state_code = "above_ma250"
    elif above_ma60:
        state_code = "above_ma60"
    elif above_ma20:
        state_code = "above_ma20"
    elif current_convergence_days >= CONVERGENCE_REQUIRED_DAYS:
        state_code = "below_ma20_converged"
    else:
        state_code = "below_ma20"

    ma_stack_code = _ma_stack_code(latest)

    date_at = lambda index: (
        _compact_date(frame.iloc[index]["trade_date"])
        if index is not None
        else None
    )
    latest_date = date_at(latest_index)
    initial_date = (
        date_at(initial_event["index"]) if initial_event is not None else None
    )
    trend_date = date_at(trend_index)
    return {
        # 中性几何：均线排列顺序，纯结构性事实
        "maStackCode": ma_stack_code,
        "stateCode": state_code,
        "aboveMa20": above_ma20,
        "aboveMa60": above_ma60,
        "aboveMa250": above_ma250,
        "separationPct": _as_percent(current_safety["separation"]),
        "separationRankPct": _as_percent(current_safety["rank"]),
        "dynamicThresholdPct": _as_percent(current_safety["threshold"]),
        "separationObservationCount": current_safety["observations"],
        "convergenceDays": current_convergence_days,
        "ma60BelowMa250Date": (
            date_at(initial_event["deathCrossIndex"])
            if initial_event is not None
            else date_at(death_crosses[-1] if death_crosses else None)
        ),
        "ma20CrossUpDate": date_at(current_warm_up_index),
        "ma60CrossUpDate": initial_date,
        "firstAboveMa250Date": trend_date,
        "ma60CrossUpToday": initial_date == latest_date,
        "aboveMa250Today": trend_date == latest_date,
        "stateAboveMa60": initial_start_active,
        "stateAboveMa250": trend_confirmed_active,
        "ma60CrossUpInvalidated": bool(
            initial_event is not None
            and not initial_start_active
            and not trend_confirmed_active
        ),
        "executionOwner": "external_monitor",
        "strategyExecutesOrders": False,
    }

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parent / "data"
OVERVIEW_PATH = DATA_DIR / "overview.json"
ALL_TOPICS_PATH = DATA_DIR / "all_topics.json"
HK_TARGETS_PATH = Path(__file__).resolve().parent / "hk_qdii_targets.json"
OUTPUT_PATH = DATA_DIR / "allocation_handoff.json"

ALLOCATION_MODE = "event_driven_satellite"
WEIGHT_FRESHNESS_MAX_CALENDAR_DAYS = 60

# 与页面一致的客观排序：按收盘价相对均线的位置分组，再按固定顺序。
MA_STATE_ORDER = [
    "above_ma250",
    "above_ma60",
    "above_ma20",
    "below_ma20_converged",
    "below_ma20",
]
VALID_STATE_CODES = set(MA_STATE_ORDER)

# 安全边际读数沿用参数台账口径：MA60/MA250 间距历史分位达到 70 视为达标。
SAFETY_MARGIN_RANK_PCT = 70

# 文案只陈述「读数到了哪档」，不写方向判断，也不替外部下建议。
REASON_TEXT = {
    "MA60_CROSSUP_INVALIDATED": "MA60 上穿后重新回落，交叉记录失效",
    "ABOVE_MA250_STATE": "收盘位于 MA250 上方",
    "TREND_CONFIRMED_ACTIVE": "MA250 上方状态已连续两日成立",
    "ABOVE_MA60_STATE": "收盘位于 MA60 上方",
    "MA60_MA250_SEPARATION_MET": "MA60 与 MA250 间距达到动态门槛",
    "RELATIVE_EXCESS_MET": "相对收益或位置读数达到延伸刻度",
    "NO_MA_SIGNAL": "三组读数均未达门槛",
    "POSITION_WINDOW_MET": "低于 MA250 5% 的天数与 MA60 3% 区间同时达到门槛",
    "THREE_GROUPS_MET": "位置、量价、成分三组读数均达到门槛",
    "TWO_DAYS_BELOW_MA20": "连续两日收盘低于 MA20，且 MA20 下行",
    "CLOSE_BELOW_MA60": "收盘跌破 MA60",
    "ENTRY_BLOCKED_STALE_COMPONENTS": "成分数据不完整，不提供新开与加仓读数",
    "ENTRY_BLOCKED_INSUFFICIENT_HISTORY": "长周期历史样本不足，不提供新开与加仓读数",
    "ENTRY_BLOCKED_STALE_WEIGHTS": "权重快照已过期，不提供依赖龙头排名的新开与加仓读数",
    "STALE_COMPONENTS_PRESENT": "存在停牌或未更新的成分股，已按口径排除",
}


def _as_bool(value: object) -> bool:
    return value is True


def _component_freshness(topic: dict[str, Any], as_of: str) -> tuple[bool, int, int, int]:
    components = topic.get("components", topic.get("constituents", []))
    fresh_count = sum(component.get("dataFresh") is True for component in components)
    stale_count = sum(component.get("dataFresh") is False for component in components)
    unknown_count = len(components) - fresh_count - stale_count
    topic_is_fresh = topic.get("meta", {}).get("latestDate") == as_of
    return topic_is_fresh, fresh_count, stale_count, unknown_count


def _weight_freshness(topic: dict[str, Any], as_of: str) -> tuple[str | None, int | None, bool]:
    meta = topic.get("meta", {})
    weight_date = meta.get("weightDate", meta.get("constituentDate"))
    if not isinstance(weight_date, str):
        return None, None, False
    try:
        age_days = (
            datetime.strptime(as_of, "%Y%m%d")
            - datetime.strptime(weight_date, "%Y%m%d")
        ).days
    except ValueError:
        return weight_date, None, False
    return (
        weight_date,
        age_days,
        0 <= age_days <= WEIGHT_FRESHNESS_MAX_CALENDAR_DAYS,
    )


def _market_state(topic: dict[str, Any]) -> dict[str, bool]:
    chart = topic.get("chart", [])
    latest = chart[-1] if chart else {}
    close = latest.get("close")
    ma20 = latest.get("ma20")
    ma60 = latest.get("ma60")
    ma60_observation_window = (
        isinstance(close, (int, float))
        and isinstance(ma60, (int, float))
        and close >= ma60 * 0.97
    )
    close_below_ma60 = (
        isinstance(close, (int, float))
        and isinstance(ma60, (int, float))
        and close < ma60
    )
    last_two_below_ma20 = len(chart) >= 2 and all(
        isinstance(row.get("close"), (int, float))
        and isinstance(row.get("ma20"), (int, float))
        and row["close"] < row["ma20"]
        for row in chart[-2:]
    )
    ma20_weakening = (
        len(chart) >= 6
        and isinstance(ma20, (int, float))
        and isinstance(chart[-6].get("ma20"), (int, float))
        and ma20 < chart[-6]["ma20"]
    )
    return {
        "withinMa60Window": ma60_observation_window,
        "closeBelowMa60": close_below_ma60,
        "twoDaysBelowMa20": last_two_below_ma20 and ma20_weakening,
    }


def _three_stages_passed(topic: dict[str, Any]) -> bool:
    stages = {stage.get("id"): stage for stage in topic.get("stages", [])}
    return all(
        _as_bool(stages.get(stage_id, {}).get("passed"))
        for stage_id in ("structure", "breakout", "leader")
    )


def _state_reading(
    lifecycle: dict[str, Any],
    market: dict[str, bool],
    entry_guard_reasons: list[str],
    three_stages_passed: bool,
    states: dict[str, Any],
) -> list[str]:
    """把当前行情事实归入互斥的一档读数；只描述位置与门槛，不带动作语义。"""
    initial_active = _as_bool(lifecycle.get("stateAboveMa60"))
    trend_active = _as_bool(lifecycle.get("stateAboveMa250"))
    initial_invalidated = _as_bool(lifecycle.get("ma60CrossUpInvalidated"))
    confirmed_quality = trend_active and three_stages_passed

    if initial_invalidated or (
        market["closeBelowMa60"] and (initial_active or trend_active)
    ):
        codes = ["CLOSE_BELOW_MA60"]
        if initial_invalidated:
            codes.insert(0, "MA60_CROSSUP_INVALIDATED")
        return codes

    if entry_guard_reasons:
        return list(entry_guard_reasons)

    if trend_active and market["twoDaysBelowMa20"]:
        return ["TREND_CONFIRMED_ACTIVE", "TWO_DAYS_BELOW_MA20"]

    if confirmed_quality:
        return ["ABOVE_MA250_STATE", "THREE_GROUPS_MET"]

    if initial_active:
        codes = ["ABOVE_MA60_STATE"]
        separation_rank = lifecycle.get("separationRankPct")
        if isinstance(separation_rank, (int, float)) and separation_rank >= SAFETY_MARGIN_RANK_PCT:
            codes.append("MA60_MA250_SEPARATION_MET")
        return codes

    # 观察层已不再输出 label。这里从 summary.stateInputs 的【事实输入】自行推导，
    # 保证本文件不依赖观察层的措辞，也不替外部监测端下结论。
    approaching_start = bool(
        states.get("belowMa250FiveDaysGe60")
        and states.get("ma60CrossUpEmerged")
        and states.get("leaderGroupMonitored")
    )
    trend_extension = bool(
        states.get("ma250ExceedPct15")
        or states.get("relativeExcessGe15Pct")
        or states.get("nearWindowHighBreadth")
    )

    if approaching_start and market["withinMa60Window"]:
        return ["POSITION_WINDOW_MET"]

    if trend_extension:
        return ["RELATIVE_EXCESS_MET"]

    return ["NO_MA_SIGNAL"]


def _reason_codes(
    state_reading: list[str],
    stale_component_count: int,
) -> list[str]:
    """只保留与状态归类和数据质量相关的读数；资金与拥挤度分位已于 2026-09-21 下线。"""
    codes = list(state_reading)
    if stale_component_count:
        codes.append("STALE_COMPONENTS_PRESENT")
    return codes


def _topic_map(
    core_topics: list[dict[str, Any]],
    hk_topics: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    topics = core_topics + hk_topics
    result = {
        str(topic.get("target", {}).get("code")): topic
        for topic in topics
        if topic.get("target", {}).get("code")
    }
    if len(result) != len(topics):
        raise ValueError("Allocation handoff source topics contain duplicate or missing codes.")
    return result


def build_allocation_handoff(
    overview: dict[str, Any],
    core_topics: list[dict[str, Any]],
    hk_topics: list[dict[str, Any]],
) -> dict[str, Any]:
    overview_targets = overview.get("targets", [])
    as_of_dates = {item.get("latestDate") for item in overview_targets}
    if len(as_of_dates) != 1 or not next(iter(as_of_dates), None):
        raise ValueError("Overview must have one shared latestDate for allocation handoff.")
    as_of = str(next(iter(as_of_dates)))
    topics_by_code = _topic_map(core_topics, hk_topics)

    targets: list[dict[str, Any]] = []
    for item in overview_targets:
        code = str(item.get("code"))
        topic = topics_by_code.get(code)
        if topic is None:
            raise ValueError(f"Allocation handoff is missing source topic for {code}.")
        summary = topic.get("summary", {})
        lifecycle = summary.get("maLifecycle", {})
        topic_data_fresh, fresh_count, stale_count, unknown_count = _component_freshness(
            topic, as_of
        )
        entry_data_fresh = (
            topic_data_fresh
            and fresh_count > 0
            and stale_count == 0
            and unknown_count == 0
        )
        topic_meta = topic.get("meta", {})
        history_ready = topic_meta.get("longCycleHistoryReady") is True
        weight_date, weight_age_days, weight_fresh = _weight_freshness(topic, as_of)
        entry_guard_reasons: list[str] = []
        if not entry_data_fresh:
            entry_guard_reasons.append("ENTRY_BLOCKED_STALE_COMPONENTS")
        if not history_ready:
            entry_guard_reasons.append("ENTRY_BLOCKED_INSUFFICIENT_HISTORY")
        if not weight_fresh:
            entry_guard_reasons.append("ENTRY_BLOCKED_STALE_WEIGHTS")
        entry_guard_passed = not entry_guard_reasons
        etf_liquidity_applicable = item.get("kind") == "etf"
        etf_amount_rank_pct = summary.get("etfAmountRankPct")
        etf_liquidity_data_ready = (
            isinstance(etf_amount_rank_pct, (int, float))
            if etf_liquidity_applicable
            else False
        )
        market = _market_state(topic)
        stage_all_passed = _three_stages_passed(topic)
        states = summary.get("stateInputs") or {}
        state_reading = _state_reading(
            lifecycle, market, entry_guard_reasons, stage_all_passed, states
        )
        reason_codes = _reason_codes(state_reading, stale_count)
        ma_event_today = _as_bool(lifecycle.get("ma60CrossUpToday")) or _as_bool(
            lifecycle.get("aboveMa250Today")
        )
        targets.append(
            {
                "code": code,
                "name": item.get("name"),
                "slug": item.get("slug"),
                "kind": item.get("kind"),
                "bucket": item.get("bucket"),
                "route": item.get("route"),
                "asOf": as_of,
                "maStackCode": lifecycle.get("maStackCode"),
                "maStateCode": lifecycle.get("stateCode"),
                "maEventToday": ma_event_today,
                "stateInputs": states,
                "signal": {
                    "ma60CrossUpToday": _as_bool(lifecycle.get("ma60CrossUpToday")),
                    "stateAboveMa60": _as_bool(lifecycle.get("stateAboveMa60")),
                    "ma60CrossUpInvalidated": _as_bool(
                        lifecycle.get("ma60CrossUpInvalidated")
                    ),
                    "aboveMa250Today": _as_bool(lifecycle.get("aboveMa250Today")),
                    "stateAboveMa250": _as_bool(lifecycle.get("stateAboveMa250")),
                    "ma60CrossUpDate": lifecycle.get("ma60CrossUpDate"),
                    "firstAboveMa250Date": lifecycle.get("firstAboveMa250Date"),
                },
                "guards": {
                    "topicDataFresh": topic_data_fresh,
                    "freshComponentCount": fresh_count,
                    "staleComponentCount": stale_count,
                    "unknownComponentFreshnessCount": unknown_count,
                    "entryDataFresh": entry_data_fresh,
                    "entryGuardPassed": entry_guard_passed,
                    "longCycleHistoryReady": history_ready,
                    "historyStartDate": topic_meta.get("dataStart"),
                    "historyTradeDayCount": topic_meta.get("historyTradeDayCount"),
                    "ma250ValidDayCount": topic_meta.get("ma250ValidDayCount"),
                    "weightDate": weight_date,
                    "weightAgeCalendarDays": weight_age_days,
                    "weightFresh": weight_fresh,
                    "weightFreshnessMaxCalendarDays": WEIGHT_FRESHNESS_MAX_CALENDAR_DAYS,
                    "etfLiquidityApplicable": etf_liquidity_applicable,
                    "etfLiquidityDataReady": etf_liquidity_data_ready,
                    "etfAmountRankPct": etf_amount_rank_pct,
                    "premiumDiscountCheckProvided": False,
                    "premiumDiscountCheckOwner": "external_monitor",
                    "withinMa60Window": market["withinMa60Window"],
                    "closeBelowMa60": market["closeBelowMa60"],
                    "twoDaysBelowMa20": market["twoDaysBelowMa20"],
                    "threeGroupsMet": stage_all_passed,
                },
                "reasonCodes": reason_codes,
                "reasons": [REASON_TEXT[code] for code in reason_codes],
                "stagePassCount": summary.get("stagePassCount", item.get("stagePassCount", 0)),
                "absorptionRankPct": summary.get(
                    "absorptionRankPct", item.get("absorptionRankPct")
                ),
                "targetOrder": item.get("order"),
            }
        )

    targets.sort(
        key=lambda item: (
            MA_STATE_ORDER.index(item["maStateCode"])
            if item["maStateCode"] in MA_STATE_ORDER
            else len(MA_STATE_ORDER),
            int(item.get("targetOrder") or 0),
        )
    )
    meta = overview.get("meta", {})
    return {
        "meta": {
            "schemaVersion": "2.0",
            "generatedAt": meta.get("generatedAt"),
            "asOf": as_of,
            "targetCount": len(targets),
            "executionOwner": "external_monitor",
            "allocationMode": ALLOCATION_MODE,
            "allocationUnitOwner": "external_monitor",
            "strategyExecutesOrders": False,
            "positionSizingProvided": False,
            "fixedCnyAmountProvided": False,
            "leaderConfirmationRole": "industry_state_confirmation_only",
            "leaderStockChaseAllowed": False,
            "etfLiquidityDecisionOwner": "external_monitor",
        },
        "targets": targets,
    }


def validate_allocation_handoff(
    handoff: dict[str, Any],
    expected_codes: set[str],
    end_date: str,
) -> list[str]:
    issues: list[str] = []
    meta = handoff.get("meta", {})
    targets = handoff.get("targets", [])
    if meta.get("schemaVersion") != "2.0":
        issues.append("Allocation handoff schemaVersion is invalid.")
    if meta.get("asOf") != end_date:
        issues.append("Allocation handoff asOf does not equal end_date.")
    if meta.get("targetCount") != len(expected_codes):
        issues.append("Allocation handoff targetCount is invalid.")
    if meta.get("executionOwner") != "external_monitor":
        issues.append("Allocation handoff executionOwner is invalid.")
    if meta.get("allocationMode") != ALLOCATION_MODE:
        issues.append("Allocation handoff allocationMode is invalid.")
    if meta.get("allocationUnitOwner") != "external_monitor":
        issues.append("Allocation handoff allocationUnitOwner is invalid.")
    if meta.get("strategyExecutesOrders") is not False:
        issues.append("Allocation handoff must not execute orders.")
    if meta.get("positionSizingProvided") is not False:
        issues.append("Allocation handoff must not provide position sizing.")
    if meta.get("fixedCnyAmountProvided") is not False:
        issues.append("Allocation handoff must not provide a fixed CNY amount.")
    if meta.get("leaderConfirmationRole") != "industry_state_confirmation_only":
        issues.append("Allocation handoff leaderConfirmationRole is invalid.")
    if meta.get("leaderStockChaseAllowed") is not False:
        issues.append("Allocation handoff must not suggest chasing leader stocks.")
    if meta.get("etfLiquidityDecisionOwner") != "external_monitor":
        issues.append("Allocation handoff ETF liquidity owner is invalid.")

    handoff_codes = {item.get("code") for item in targets}
    if handoff_codes != expected_codes:
        issues.append("Allocation handoff codes do not match the target universe.")
    for item in targets:
        code = item.get("code", "unknown")
        if item.get("asOf") != end_date:
            issues.append(f"{code}: allocation handoff asOf is invalid.")
        if item.get("maStateCode") not in VALID_STATE_CODES:
            issues.append(f"{code}: allocation handoff maStateCode is invalid.")
        if not isinstance(item.get("maEventToday"), bool):
            issues.append(f"{code}: allocation handoff maEventToday must be boolean.")
        if not isinstance(item.get("stateInputs"), dict):
            issues.append(f"{code}: allocation handoff stateInputs is invalid.")
        signal = item.get("signal", {})
        required_signal_fields = {
            "ma60CrossUpToday",
            "stateAboveMa60",
            "ma60CrossUpInvalidated",
            "aboveMa250Today",
            "stateAboveMa250",
            "ma60CrossUpDate",
            "firstAboveMa250Date",
        }
        missing_signal_fields = sorted(required_signal_fields.difference(signal))
        if missing_signal_fields:
            issues.append(
                f"{code}: allocation handoff signal is missing "
                f"{', '.join(missing_signal_fields)}."
            )
        else:
            for field in (
                "ma60CrossUpToday",
                "stateAboveMa60",
                "ma60CrossUpInvalidated",
                "aboveMa250Today",
                "stateAboveMa250",
            ):
                if not isinstance(signal.get(field), bool):
                    issues.append(f"{code}: allocation handoff signal {field} must be boolean.")
        if not isinstance(item.get("reasonCodes"), list) or not item["reasonCodes"]:
            issues.append(f"{code}: allocation handoff reasonCodes are invalid.")
        guards = item.get("guards", {})
        for field in [
            "topicDataFresh",
            "entryDataFresh",
            "entryGuardPassed",
            "longCycleHistoryReady",
            "weightFresh",
            "etfLiquidityApplicable",
            "etfLiquidityDataReady",
            "premiumDiscountCheckProvided",
            "withinMa60Window",
            "closeBelowMa60",
            "twoDaysBelowMa20",
            "threeGroupsMet",
        ]:
            if not isinstance(guards.get(field), bool):
                issues.append(f"{code}: allocation handoff guard {field} must be boolean.")
        if guards.get("weightFreshnessMaxCalendarDays") != WEIGHT_FRESHNESS_MAX_CALENDAR_DAYS:
            issues.append(f"{code}: allocation handoff weight freshness threshold is invalid.")
        weight_age = guards.get("weightAgeCalendarDays")
        if isinstance(weight_age, int) and weight_age < 0:
            issues.append(f"{code}: allocation handoff weight date is after asOf.")
        elif not isinstance(weight_age, int):
            issues.append(f"{code}: allocation handoff weight age is invalid.")
        history_days = guards.get("historyTradeDayCount")
        ma250_days = guards.get("ma250ValidDayCount")
        if not isinstance(guards.get("historyStartDate"), str):
            issues.append(f"{code}: allocation handoff historyStartDate is invalid.")
        if not isinstance(history_days, int) or history_days <= 0:
            issues.append(f"{code}: allocation handoff historyTradeDayCount is invalid.")
        if not isinstance(ma250_days, int) or ma250_days < 0:
            issues.append(f"{code}: allocation handoff ma250ValidDayCount is invalid.")
        if guards.get("longCycleHistoryReady") is True and (
            not isinstance(history_days, int)
            or history_days < 750
            or not isinstance(ma250_days, int)
            or ma250_days < 501
        ):
            issues.append(f"{code}: allocation handoff long-cycle history is inconsistent.")
        if guards.get("premiumDiscountCheckOwner") != "external_monitor":
            issues.append(f"{code}: allocation handoff premium/discount owner is invalid.")
        if guards.get("etfLiquidityApplicable") is True and (
            guards.get("etfLiquidityDataReady") is not True
            or not isinstance(guards.get("etfAmountRankPct"), (int, float))
        ):
            issues.append(f"{code}: allocation handoff ETF liquidity data is incomplete.")
    return issues


def main() -> None:
    overview = json.loads(OVERVIEW_PATH.read_text(encoding="utf-8"))
    core_topics = json.loads(ALL_TOPICS_PATH.read_text(encoding="utf-8"))
    hk_targets = json.loads(HK_TARGETS_PATH.read_text(encoding="utf-8"))
    hk_topics = [
        json.loads((Path(__file__).resolve().parent / target["dataFile"]).read_text(encoding="utf-8"))
        for target in hk_targets
    ]
    handoff = build_allocation_handoff(overview, core_topics, hk_topics)
    OUTPUT_PATH.write_text(
        json.dumps(handoff, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()

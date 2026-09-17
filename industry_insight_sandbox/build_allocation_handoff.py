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

ACTION_ORDER = {
    "de_risk": 0,
    "reduce_to_one_unit": 1,
    "scale_in_eligible": 2,
    "starter_eligible": 3,
    "candidate_entry": 4,
    "hold_and_monitor": 5,
    "observe_only": 6,
}
ENTRY_ACTIONS = {"scale_in_eligible", "starter_eligible", "candidate_entry"}
VALID_ACTIONS = set(ACTION_ORDER)
ALLOCATION_MODE = "event_driven_satellite"
WEIGHT_FRESHNESS_MAX_CALENDAR_DAYS = 60
ALLOCATION_UNITS = {
    "observe_only": 0,
    "candidate_entry": 0.5,
    "starter_eligible": 1,
    "scale_in_eligible": 2,
    "reduce_to_one_unit": 1,
    "hold_and_monitor": None,
    "de_risk": 0,
}
ALLOCATION_INSTRUCTIONS = {
    "observe_only": "no_satellite_position",
    "candidate_entry": "candidate_half_unit_only",
    "starter_eligible": "target_one_starter_unit",
    "scale_in_eligible": "target_two_units_total",
    "reduce_to_one_unit": "reduce_to_one_unit_if_held",
    "hold_and_monitor": "hold_existing_only",
    "de_risk": "target_zero_units",
}

REASON_TEXT = {
    "INITIAL_START_INVALIDATED": "MA60 初始启动已失效",
    "TREND_CONFIRMED_ACTIVE": "MA250 年线趋势确认仍有效",
    "INITIAL_START_ACTIVE": "MA60 初始启动仍有效",
    "SAFETY_MARGIN_PASSED": "MA60 与 MA250 的安全边际已通过",
    "TREND_EXTENSION": "当前属于趋势延续，供外部持仓管理",
    "OBSERVE_ONLY": "尚未形成可执行的均线生命周期信号",
    "CANDIDATE_ENTRY_QUALITY_GATE": "主策略接近启动且已进入 MA60 观察窗口",
    "THREE_STAGE_CONFIRMATION": "低位、资金与龙头三层条件均已通过",
    "MA20_PROFIT_PROTECTION": "连续两日收盘低于 MA20，且 MA20 走弱",
    "MA60_STRUCTURE_EXIT": "收盘跌破 MA60，趋势结构退出",
    "ENTRY_BLOCKED_STALE_COMPONENTS": "成分数据不完整，不建议新开或加仓",
    "ENTRY_BLOCKED_INSUFFICIENT_HISTORY": "长周期历史样本不足，不建议新开或加仓",
    "ENTRY_BLOCKED_STALE_WEIGHTS": "权重快照已过期，不建议依据龙头排名新开或加仓",
    "FUNDING_CONFIRMED": "资金连续三日确认",
    "CROWDING_HOT": "资金拥挤风险提示",
    "STALE_COMPONENTS_PRESENT": "存在停牌或未更新的成分股，已按策略排除失效数据",
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
        "ma60ObservationWindow": ma60_observation_window,
        "closeBelowMa60": close_below_ma60,
        "ma20ProfitProtection": last_two_below_ma20 and ma20_weakening,
    }


def _three_stages_passed(topic: dict[str, Any]) -> bool:
    stages = {stage.get("id"): stage for stage in topic.get("stages", [])}
    return all(
        _as_bool(stages.get(stage_id, {}).get("passed"))
        for stage_id in ("structure", "breakout", "leader")
    )


def _position_signal(
    summary: dict[str, Any],
    lifecycle: dict[str, Any],
    market: dict[str, bool],
    entry_guard_reasons: list[str],
    three_stages_passed: bool,
) -> tuple[str, dict[str, Any]]:
    initial_active = _as_bool(lifecycle.get("initialStartActive"))
    trend_active = _as_bool(lifecycle.get("trendConfirmedActive"))
    initial_invalidated = _as_bool(lifecycle.get("initialStartInvalidated"))
    confirmed_quality = trend_active and three_stages_passed

    def signal(
        stage: str,
        units: float | int | None,
        entry_action: str,
        risk_action: str,
        reason_codes: list[str],
        risk_reason_codes: list[str] | None = None,
        *,
        new_entry_allowed: bool = False,
        add_position_allowed: bool = False,
    ) -> dict[str, Any]:
        return {
            "stage": stage,
            "referenceUnits": units,
            "newEntryAllowed": new_entry_allowed,
            "addPositionAllowed": add_position_allowed,
            "entryAction": entry_action,
            "riskAction": risk_action,
            "reasonCodes": reason_codes,
            "riskReasonCodes": risk_reason_codes or [],
            "requiresExternalPositionState": True,
            "leaderConfirmationRole": "industry_state_confirmation_only",
            "leaderStockChaseAllowed": False,
            "executionOwner": "external_monitor",
        }

    if initial_invalidated or (
        market["closeBelowMa60"] and (initial_active or trend_active)
    ):
        reasons = ["MA60_STRUCTURE_EXIT"]
        if initial_invalidated:
            reasons.insert(0, "INITIAL_START_INVALIDATED")
        return "de_risk", signal(
            "exit",
            0,
            "no_entry",
            "exit_to_zero_if_held",
            reasons,
            reasons,
        )

    if entry_guard_reasons:
        return "hold_and_monitor", signal(
            "data_guard",
            None,
            "no_entry",
            "hold",
            entry_guard_reasons,
        )

    if trend_active and market["ma20ProfitProtection"]:
        reasons = ["TREND_CONFIRMED_ACTIVE", "MA20_PROFIT_PROTECTION"]
        return "reduce_to_one_unit", signal(
            "risk_protection",
            1,
            "no_entry",
            "reduce_to_one_unit_if_held",
            reasons,
            ["MA20_PROFIT_PROTECTION"],
        )

    if confirmed_quality:
        return "scale_in_eligible", signal(
            "confirmed",
            2,
            "scale_to_two_units",
            "hold",
            ["TREND_CONFIRMED_ACTIVE", "THREE_STAGE_CONFIRMATION"],
            new_entry_allowed=True,
            add_position_allowed=True,
        )

    if initial_active:
        reasons = ["INITIAL_START_ACTIVE"]
        if _as_bool(lifecycle.get("safetyMarginPassed")):
            reasons.append("SAFETY_MARGIN_PASSED")
        return "starter_eligible", signal(
            "starter",
            1,
            "enter_or_hold_starter",
            "hold",
            reasons,
            new_entry_allowed=True,
        )

    if (
        summary.get("label") == "接近启动"
        and market["ma60ObservationWindow"]
    ):
        return "candidate_entry", signal(
            "candidate",
            0.5,
            "candidate_entry",
            "hold",
            ["CANDIDATE_ENTRY_QUALITY_GATE"],
            new_entry_allowed=True,
        )

    if summary.get("label") == "趋势延续":
        return "hold_and_monitor", signal(
            "extended",
            None,
            "hold_existing_only",
            "hold",
            ["TREND_EXTENSION"],
        )

    return "observe_only", signal(
        "watch",
        0,
        "no_entry",
        "hold",
        ["OBSERVE_ONLY"],
    )


def _reason_codes(
    position_signal: dict[str, Any],
    summary: dict[str, Any],
    stale_component_count: int,
) -> list[str]:
    codes = list(position_signal["reasonCodes"])
    if _as_bool(summary.get("fundingConfirmed")):
        codes.append("FUNDING_CONFIRMED")
    if _as_bool(summary.get("crowdingHot")):
        codes.append("CROWDING_HOT")
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
        action, position_signal = _position_signal(
            summary,
            lifecycle,
            market,
            entry_guard_reasons,
            stage_all_passed,
        )
        reason_codes = _reason_codes(position_signal, summary, stale_count)
        action_event_today = _as_bool(lifecycle.get("initialStartToday")) or _as_bool(
            lifecycle.get("trendConfirmedToday")
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
                "action": action,
                "actionEventToday": action_event_today,
                "entryPriorityRank": None,
                "targetAllocationUnits": ALLOCATION_UNITS[action],
                "allocationInstruction": ALLOCATION_INSTRUCTIONS[action],
                "positionSignal": position_signal,
                "primaryLabel": summary.get("label", item.get("label")),
                "lifecycleLabel": lifecycle.get("label", item.get("maLifecycleLabel")),
                "signal": {
                    "capitalInterface": lifecycle.get(
                        "capitalInterface", item.get("capitalInterface")
                    ),
                    "initialStartToday": _as_bool(lifecycle.get("initialStartToday")),
                    "initialStartActive": _as_bool(lifecycle.get("initialStartActive")),
                    "initialStartInvalidated": _as_bool(
                        lifecycle.get("initialStartInvalidated")
                    ),
                    "trendConfirmedToday": _as_bool(
                        lifecycle.get("trendConfirmedToday")
                    ),
                    "trendConfirmedActive": _as_bool(
                        lifecycle.get("trendConfirmedActive")
                    ),
                    "initialStartDate": lifecycle.get("initialStartDate"),
                    "trendConfirmedDate": lifecycle.get("trendConfirmedDate"),
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
                    "fundingConfirmed": _as_bool(summary.get("fundingConfirmed")),
                    "crowdingHot": _as_bool(summary.get("crowdingHot")),
                    "ma60ObservationWindow": market["ma60ObservationWindow"],
                    "closeBelowMa60": market["closeBelowMa60"],
                    "ma20ProfitProtection": market["ma20ProfitProtection"],
                    "threeStagesPassed": stage_all_passed,
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

    entry_targets = [item for item in targets if item["action"] in ENTRY_ACTIONS]
    entry_targets.sort(
        key=lambda item: (
            ACTION_ORDER[item["action"]],
            -int(item.get("stagePassCount") or 0),
            -float(item.get("absorptionRankPct") or 0),
            int(item.get("targetOrder") or 0),
        )
    )
    for rank, item in enumerate(entry_targets, start=1):
        item["entryPriorityRank"] = rank

    targets.sort(
        key=lambda item: (
            ACTION_ORDER[item["action"]],
            item["entryPriorityRank"] or 10_000,
            int(item.get("targetOrder") or 0),
        )
    )
    meta = overview.get("meta", {})
    return {
        "meta": {
            "schemaVersion": "1.3",
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
    if meta.get("schemaVersion") != "1.3":
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
    ranks = sorted(
        item["entryPriorityRank"]
        for item in targets
        if item.get("entryPriorityRank") is not None
    )
    if ranks != list(range(1, len(ranks) + 1)):
        issues.append("Allocation handoff entryPriorityRank is not contiguous.")
    for item in targets:
        code = item.get("code", "unknown")
        if item.get("asOf") != end_date:
            issues.append(f"{code}: allocation handoff asOf is invalid.")
        if item.get("action") not in VALID_ACTIONS:
            issues.append(f"{code}: allocation handoff action is invalid.")
            continue
        action = item["action"]
        if not isinstance(item.get("actionEventToday"), bool):
            issues.append(f"{code}: allocation handoff actionEventToday must be boolean.")
        if item.get("targetAllocationUnits") != ALLOCATION_UNITS[action]:
            issues.append(f"{code}: allocation handoff targetAllocationUnits is invalid.")
        if item.get("allocationInstruction") != ALLOCATION_INSTRUCTIONS[action]:
            issues.append(f"{code}: allocation handoff allocationInstruction is invalid.")
        position_signal = item.get("positionSignal", {})
        required_position_fields = {
            "stage",
            "referenceUnits",
            "newEntryAllowed",
            "addPositionAllowed",
            "entryAction",
            "riskAction",
            "reasonCodes",
            "riskReasonCodes",
            "requiresExternalPositionState",
            "leaderConfirmationRole",
            "leaderStockChaseAllowed",
            "executionOwner",
        }
        missing_position_fields = sorted(required_position_fields.difference(position_signal))
        if missing_position_fields:
            issues.append(
                f"{code}: allocation handoff positionSignal is missing "
                f"{', '.join(missing_position_fields)}."
            )
        elif (
            position_signal.get("referenceUnits") != ALLOCATION_UNITS[action]
            or not isinstance(position_signal.get("newEntryAllowed"), bool)
            or not isinstance(position_signal.get("addPositionAllowed"), bool)
            or not isinstance(position_signal.get("reasonCodes"), list)
            or not isinstance(position_signal.get("riskReasonCodes"), list)
            or position_signal.get("requiresExternalPositionState") is not True
            or position_signal.get("leaderConfirmationRole")
            != "industry_state_confirmation_only"
            or position_signal.get("leaderStockChaseAllowed") is not False
            or position_signal.get("executionOwner") != "external_monitor"
        ):
            issues.append(f"{code}: allocation handoff positionSignal is invalid.")
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
            "fundingConfirmed",
            "crowdingHot",
            "ma60ObservationWindow",
            "closeBelowMa60",
            "ma20ProfitProtection",
            "threeStagesPassed",
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
        if item.get("action") in ENTRY_ACTIONS and guards.get("entryGuardPassed") is not True:
            issues.append(f"{code}: allocation handoff entry action bypasses data guards.")
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

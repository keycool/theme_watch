from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OVERVIEW_PATH = DATA_DIR / "overview.json"
ALL_TOPICS_PATH = DATA_DIR / "all_topics.json"
HK_TARGETS_PATH = ROOT / "hk_qdii_targets.json"
OUTPUT_PATH = DATA_DIR / "signal_followup.json"
HORIZONS = (5, 20, 60)
SIGNAL_LABEL = "启动确认"


def _topic_map(
    core_topics: list[dict[str, Any]],
    hk_topics: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        str(topic["target"]["code"]): topic
        for topic in core_topics + hk_topics
    }


def _normalized_fields(topic: dict[str, Any]) -> tuple[str, str, str]:
    target = topic.get("target", {})
    if target.get("benchmarkCode"):
        return "etfNormalized", "benchmarkNormalized", str(target["benchmarkCode"])
    return "themeNormalized", "benchmarkNormalized", "000300.SH"


def _new_event(topic: dict[str, Any], as_of: str) -> dict[str, Any]:
    target_field, benchmark_field, benchmark_code = _normalized_fields(topic)
    chart = topic.get("chart", [])
    row = next((item for item in chart if item.get("date") == as_of), None)
    if row is None:
        raise ValueError(f"{topic['target']['code']}: signal date is absent from chart.")
    if not isinstance(row.get(target_field), (int, float)) or not isinstance(
        row.get(benchmark_field), (int, float)
    ):
        raise ValueError(f"{topic['target']['code']}: normalized prices are missing.")
    code = str(topic["target"]["code"])
    return {
        "eventId": f"{code}:{as_of}",
        "code": code,
        "name": topic["target"].get("name"),
        "signalDate": as_of,
        "signalLabel": SIGNAL_LABEL,
        "benchmarkCode": benchmark_code,
        "sourceTargetNormalized": row[target_field],
        "sourceBenchmarkNormalized": row[benchmark_field],
        "horizons": {
            str(horizon): {"status": "pending"} for horizon in HORIZONS
        },
    }


def _update_event(event: dict[str, Any], topic: dict[str, Any], as_of: str) -> None:
    target_field, benchmark_field, benchmark_code = _normalized_fields(topic)
    if event.get("benchmarkCode") != benchmark_code:
        raise ValueError(f"{event.get('eventId')}: benchmark changed after signal.")
    chart = topic.get("chart", [])
    dates = [str(row.get("date")) for row in chart]
    signal_date = str(event["signalDate"])
    if signal_date not in dates:
        return
    source_index = dates.index(signal_date)
    for horizon in HORIZONS:
        result = event["horizons"][str(horizon)]
        if result.get("status") == "complete":
            continue
        end_index = source_index + horizon
        if end_index >= len(chart):
            continue
        end_row = chart[end_index]
        end_date = str(end_row.get("date"))
        if end_date > as_of:
            raise ValueError(f"{event.get('eventId')}: future row entered follow-up.")
        target_end = end_row.get(target_field)
        benchmark_end = end_row.get(benchmark_field)
        if not isinstance(target_end, (int, float)) or not isinstance(
            benchmark_end, (int, float)
        ):
            continue
        target_return = target_end / event["sourceTargetNormalized"] - 1
        benchmark_return = benchmark_end / event["sourceBenchmarkNormalized"] - 1
        path_returns = []
        path_excess = []
        for path_row in chart[source_index + 1 : end_index + 1]:
            path_target = path_row.get(target_field)
            path_benchmark = path_row.get(benchmark_field)
            if not isinstance(path_target, (int, float)) or not isinstance(
                path_benchmark, (int, float)
            ):
                continue
            target_path_return = path_target / event["sourceTargetNormalized"] - 1
            benchmark_path_return = (
                path_benchmark / event["sourceBenchmarkNormalized"] - 1
            )
            path_returns.append(target_path_return)
            path_excess.append(target_path_return - benchmark_path_return)
        result.update(
            {
                "status": "complete",
                "endDate": end_date,
                "targetReturnPct": round(target_return * 100, 4),
                "benchmarkReturnPct": round(benchmark_return * 100, 4),
                "excessReturnPct": round((target_return - benchmark_return) * 100, 4),
                "maxAdverseTargetReturnPct": round(min(path_returns) * 100, 4),
                "maxAdverseExcessReturnPct": round(min(path_excess) * 100, 4),
            }
        )


def _summary(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for horizon in HORIZONS:
        completed = [
            event["horizons"][str(horizon)]
            for event in events
            if event["horizons"][str(horizon)].get("status") == "complete"
        ]
        positive = sum(item["excessReturnPct"] > 0 for item in completed)
        excess_values = [item["excessReturnPct"] for item in completed]
        adverse_values = [item["maxAdverseTargetReturnPct"] for item in completed]
        summary[str(horizon)] = {
            "completedCount": len(completed),
            "positiveExcessCount": positive,
            "positiveExcessRatePct": (
                round(positive / len(completed) * 100, 2) if completed else None
            ),
            "averageExcessReturnPct": (
                round(sum(excess_values) / len(excess_values), 4)
                if excess_values
                else None
            ),
            "medianExcessReturnPct": (
                round(median(excess_values), 4) if excess_values else None
            ),
            "averageMaxAdverseTargetReturnPct": (
                round(sum(adverse_values) / len(adverse_values), 4)
                if adverse_values
                else None
            ),
        }
    return summary


def build_signal_followup(
    overview: dict[str, Any],
    core_topics: list[dict[str, Any]],
    hk_topics: list[dict[str, Any]],
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    targets = overview.get("targets", [])
    as_of_dates = {item.get("latestDate") for item in targets}
    if len(as_of_dates) != 1 or not next(iter(as_of_dates), None):
        raise ValueError("Overview must have one shared latestDate for signal follow-up.")
    as_of = str(next(iter(as_of_dates)))
    topics = _topic_map(core_topics, hk_topics)
    prior = previous or {}
    prior_as_of = prior.get("meta", {}).get("asOf")
    if isinstance(prior_as_of, str) and prior_as_of > as_of:
        raise ValueError("Signal follow-up date cannot move backwards.")
    events = list(prior.get("events", []))
    latest_labels = dict(prior.get("latestLabels", {}))

    for item in targets:
        code = str(item["code"])
        topic = topics.get(code)
        if topic is None:
            raise ValueError(f"Signal follow-up is missing topic {code}.")
        current_label = topic.get("summary", {}).get("label")
        if current_label == SIGNAL_LABEL and latest_labels.get(code) != SIGNAL_LABEL:
            event_id = f"{code}:{as_of}"
            if not any(event.get("eventId") == event_id for event in events):
                events.append(_new_event(topic, as_of))
        latest_labels[code] = current_label

    for event in events:
        topic = topics.get(str(event.get("code")))
        if topic is not None:
            _update_event(event, topic, as_of)

    events.sort(key=lambda event: (event["signalDate"], event["code"]))
    return {
        "meta": {
            "schemaVersion": "1.0",
            "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "asOf": as_of,
            "signalLabel": SIGNAL_LABEL,
            "horizonsTradeDays": list(HORIZONS),
            "decisionUse": False,
            "lookaheadAllowed": False,
            "eventCount": len(events),
        },
        "summary": _summary(events),
        "latestLabels": latest_labels,
        "events": events,
    }


def validate_signal_followup(
    followup: dict[str, Any], expected_codes: set[str], end_date: str
) -> list[str]:
    issues: list[str] = []
    meta = followup.get("meta", {})
    if meta.get("schemaVersion") != "1.0":
        issues.append("Signal follow-up schemaVersion is invalid.")
    if meta.get("asOf") != end_date:
        issues.append("Signal follow-up asOf does not equal end_date.")
    if meta.get("decisionUse") is not False or meta.get("lookaheadAllowed") is not False:
        issues.append("Signal follow-up must remain outside production decisions.")
    if set(followup.get("latestLabels", {})) != expected_codes:
        issues.append("Signal follow-up latestLabels do not match target universe.")
    for event in followup.get("events", []):
        if event.get("code") not in expected_codes:
            issues.append(f"{event.get('eventId')}: unknown target code.")
        if str(event.get("signalDate")) > end_date:
            issues.append(f"{event.get('eventId')}: signal date is in the future.")
        for horizon in HORIZONS:
            result = event.get("horizons", {}).get(str(horizon), {})
            if result.get("status") not in {"pending", "complete"}:
                issues.append(f"{event.get('eventId')}: invalid {horizon}-day status.")
            if result.get("status") == "complete" and str(result.get("endDate")) > end_date:
                issues.append(f"{event.get('eventId')}: future outcome detected.")
    return issues


def main() -> None:
    overview = json.loads(OVERVIEW_PATH.read_text(encoding="utf-8"))
    core_topics = json.loads(ALL_TOPICS_PATH.read_text(encoding="utf-8"))
    hk_targets = json.loads(HK_TARGETS_PATH.read_text(encoding="utf-8"))
    hk_topics = [
        json.loads((ROOT / target["dataFile"]).read_text(encoding="utf-8"))
        for target in hk_targets
    ]
    previous = (
        json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        if OUTPUT_PATH.exists()
        else None
    )
    followup = build_signal_followup(overview, core_topics, hk_topics, previous)
    OUTPUT_PATH.write_text(
        json.dumps(followup, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()

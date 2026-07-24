from __future__ import annotations

import argparse
import json
import locale
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
SANDBOX_DIR = ROOT / "industry_insight_sandbox"
GENERATOR = SANDBOX_DIR / "generate_dashboard_data.py"
TARGETS_PATH = SANDBOX_DIR / "targets.json"
OVERVIEW_PATH = SANDBOX_DIR / "data" / "overview.json"
ALL_TOPICS_PATH = SANDBOX_DIR / "data" / "all_topics.json"
TOPIC_DIR = SANDBOX_DIR / "data" / "topics"
SUMMARY_DIR = ROOT / "logs" / "etf_constituent_workflow"


def _default_end_date() -> str:
    now = datetime.now()
    if now.hour < 16:
        now -= timedelta(days=1)
    return now.strftime("%Y%m%d")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the isolated ETF/index constituent observation workflow."
    )
    parser.add_argument("--run-id", default="")
    parser.add_argument("--end-date", default=_default_end_date())
    parser.add_argument("--trigger-type", default="manual")
    parser.add_argument("--allow-non-trade-day", action="store_true")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate existing outputs without requesting new market data.",
    )
    return parser


def _validate_date(value: str) -> str:
    try:
        datetime.strptime(value, "%Y%m%d")
    except ValueError as exc:
        raise ValueError("--end-date must use YYYYMMDD format.") from exc
    return value


def _is_trade_day(end_date: str) -> bool:
    import tushare as ts

    token = ts.get_token()
    if not token:
        raise RuntimeError("Tushare token is not configured.")
    calendar = ts.pro_api(token).trade_cal(
        exchange="SSE",
        start_date=end_date,
        end_date=end_date,
        fields="cal_date,is_open",
    )
    if calendar.empty:
        raise RuntimeError(f"Trading calendar returned no row for {end_date}.")
    return bool(int(calendar.iloc[0]["is_open"]))


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_generator(end_date: str, log_path: Path) -> int:
    completed = subprocess.run(
        [sys.executable, str(GENERATOR), "--end-date", end_date],
        cwd=SANDBOX_DIR,
        capture_output=True,
        check=False,
    )
    output_bytes = completed.stdout or b""
    if completed.stderr:
        output_bytes += (b"\n" if output_bytes else b"") + completed.stderr
    output = _decode_output(output_bytes)
    log_path.write_text(output, encoding="utf-8")
    return completed.returncode


def _decode_output(value: bytes) -> str:
    encodings = ["utf-8", locale.getpreferredencoding(False), "gb18030"]
    for encoding in dict.fromkeys(encodings):
        try:
            return value.decode(encoding)
        except UnicodeDecodeError:
            continue
    return value.decode("utf-8", errors="replace")


def _validate_topic_freshness(topic: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    code = topic.get("target", {}).get("code", "unknown")
    as_of = topic.get("meta", {}).get("latestDate")
    if not isinstance(as_of, str) or len(as_of) != 8 or not as_of.isdigit():
        return [f"{code}: topic as_of/latestDate is invalid."]

    components = topic.get("components", [])
    component_freshness: dict[str, bool] = {}
    fresh_active_count = 0
    fresh_ma60_count = 0
    fresh_ma250_count = 0

    for component in components:
        component_code = str(component.get("code", "unknown"))
        if "latestDate" not in component:
            issues.append(f"{code}/{component_code}: component latestDate is missing.")
            continue
        latest_date = component.get("latestDate")
        if (
            not isinstance(latest_date, str)
            or len(latest_date) != 8
            or not latest_date.isdigit()
        ):
            issues.append(f"{code}/{component_code}: component latestDate is invalid.")
            continue
        if latest_date > as_of:
            issues.append(
                f"{code}/{component_code}: component latestDate {latest_date} "
                f"is later than topic as_of {as_of}."
            )

        if "dataFresh" not in component:
            issues.append(f"{code}/{component_code}: component dataFresh is missing.")
            continue
        data_fresh = component.get("dataFresh")
        if not isinstance(data_fresh, bool):
            issues.append(
                f"{code}/{component_code}: component dataFresh must be boolean."
            )
            continue
        component_freshness[component_code] = data_fresh
        if data_fresh != (latest_date == as_of):
            issues.append(
                f"{code}/{component_code}: dataFresh is inconsistent with latestDate."
            )

        if not data_fresh:
            if component.get("aboveMa60") is True:
                issues.append(
                    f"{code}/{component_code}: stale component contributes to MA60 group strength."
                )
            if component.get("aboveMa250") is True:
                issues.append(
                    f"{code}/{component_code}: stale component contributes to MA250 group strength."
                )
            continue

        pct_1d = component.get("pct1d")
        ret_5d = component.get("ret5d")
        if (
            isinstance(pct_1d, (int, float)) and pct_1d >= 5
        ) or (
            isinstance(ret_5d, (int, float)) and ret_5d >= 5
        ):
            fresh_active_count += 1
        fresh_ma60_count += int(component.get("aboveMa60") is True)
        fresh_ma250_count += int(component.get("aboveMa250") is True)

    summary = topic.get("summary", {})
    if summary.get("activeCount") != fresh_active_count:
        issues.append(f"{code}: activeCount includes stale or inconsistent components.")
    if summary.get("aboveMa60Count") != fresh_ma60_count:
        issues.append(f"{code}: aboveMa60Count includes stale or inconsistent components.")
    if summary.get("aboveMa250Count") != fresh_ma250_count:
        issues.append(f"{code}: aboveMa250Count includes stale or inconsistent components.")

    strict_leader_confirmed = False
    for event in topic.get("limitEvents", []):
        event_code = str(event.get("code", "unknown"))
        event_fresh = event.get("dataFresh")
        if not isinstance(event_fresh, bool):
            issues.append(f"{code}/{event_code}: leader event dataFresh must be boolean.")
            continue
        component_fresh = component_freshness.get(event_code)
        if component_fresh is not None and event_fresh != component_fresh:
            issues.append(
                f"{code}/{event_code}: leader event freshness disagrees with component."
            )
        if not event_fresh and event.get("qualified") is True:
            issues.append(f"{code}/{event_code}: stale component qualifies as leader.")
        if (
            event_fresh
            and event.get("qualified") is True
            and isinstance(event.get("weightRank"), int)
            and event["weightRank"] <= 3
        ):
            strict_leader_confirmed = True

    if summary.get("strictLeaderConfirmed") is not strict_leader_confirmed:
        issues.append(f"{code}: strictLeaderConfirmed is inconsistent with fresh events.")

    group_monitor_expected = bool(
        components
        and fresh_active_count >= 1
        and fresh_ma60_count / len(components) >= 0.5
    )
    leader_stage = next(
        (stage for stage in topic.get("stages", []) if stage.get("id") == "leader"),
        None,
    )
    group_item = next(
        (
            item
            for item in (leader_stage or {}).get("items", [])
            if item.get("title") == "核心群体转强"
        ),
        None,
    )
    if group_item is None:
        issues.append(f"{code}: leader group-strength item is missing.")
    elif group_item.get("passed") is not group_monitor_expected:
        issues.append(f"{code}: group-strength result includes stale components.")

    if summary.get("label") == "启动确认" and not strict_leader_confirmed:
        issues.append(f"{code}: startup confirmation lacks a fresh strict leader.")
    return issues


def _validate_outputs(end_date: str) -> tuple[list[str], dict[str, Any]]:
    issues: list[str] = []
    required = [TARGETS_PATH, OVERVIEW_PATH, ALL_TOPICS_PATH]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        return [f"Missing required output: {', '.join(missing)}"], {}

    targets = _read_json(TARGETS_PATH)
    overview = _read_json(OVERVIEW_PATH)
    topics = _read_json(ALL_TOPICS_PATH)

    expected_codes = {item["code"] for item in targets}
    overview_codes = {item["code"] for item in overview.get("targets", [])}
    topic_codes = {item.get("target", {}).get("code") for item in topics}
    expected_slugs = {
        item["code"].lower().replace(".", "-")
        for item in targets
    }
    topic_files = {path.stem for path in TOPIC_DIR.glob("*.json")}

    if len(targets) != 20:
        issues.append(f"Formal target count is {len(targets)}, expected 20.")
    if expected_codes != overview_codes:
        issues.append("Overview target codes do not match targets.json.")
    if expected_codes != topic_codes:
        issues.append("Topic target codes do not match targets.json.")
    if expected_slugs != topic_files:
        issues.append("Per-topic JSON files do not exactly match the formal target slugs.")

    meta = overview.get("meta", {})
    if meta.get("sandbox") is not True:
        issues.append("Overview is not marked as sandbox output.")
    if meta.get("targetCount") != 20:
        issues.append("Overview targetCount is not 20.")
    if meta.get("etfCount") != 19 or meta.get("indexCount") != 1:
        issues.append("Overview ETF/index counts are not 19/1.")

    overview_dates = {
        item.get("latestDate") for item in overview.get("targets", [])
    }
    if overview_dates != {end_date}:
        issues.append(
            f"Overview latest dates are {sorted(str(x) for x in overview_dates)}, "
            f"expected only {end_date}."
        )

    expected_stage_titles = ["低位收敛", "带量突破年线", "权重龙头确认"]
    fresh_component_count = 0
    stale_component_count = 0
    for topic in topics:
        target = topic.get("target", {})
        code = target.get("code", "unknown")
        if topic.get("meta", {}).get("sandbox") is not True:
            issues.append(f"{code}: topic is not marked as sandbox output.")
        if topic.get("meta", {}).get("latestDate") != end_date:
            issues.append(f"{code}: latestDate does not equal {end_date}.")
        if not target.get("indexCode") or not target.get("indexName"):
            issues.append(f"{code}: tracking index metadata is incomplete.")
        if len(topic.get("chart", [])) < 250:
            issues.append(f"{code}: chart history has fewer than 250 rows.")
        components = topic.get("components", [])
        if len(components) < 3:
            issues.append(f"{code}: fewer than 3 core components.")
        if topic.get("summary", {}).get("coreCount") != len(components):
            issues.append(f"{code}: coreCount does not match component rows.")
        issues.extend(_validate_topic_freshness(topic))
        fresh_component_count += sum(
            component.get("dataFresh") is True for component in components
        )
        stale_component_count += sum(
            component.get("dataFresh") is False for component in components
        )
        stage_titles = [stage.get("title") for stage in topic.get("stages", [])]
        if stage_titles != expected_stage_titles:
            issues.append(f"{code}: three-stage observation chain is incomplete.")
        slug = target.get("slug")
        if slug:
            individual_path = TOPIC_DIR / f"{slug}.json"
            if individual_path.exists() and _read_json(individual_path) != topic:
                issues.append(f"{code}: individual topic JSON differs from aggregate.")

    labels = Counter(
        item.get("label", "unknown") for item in overview.get("targets", [])
    )
    weight_dates = sorted(
        {item.get("weightDate") for item in overview.get("targets", [])}
    )
    metrics = {
        "target_count": len(expected_codes),
        "etf_count": meta.get("etfCount"),
        "index_count": meta.get("indexCount"),
        "latest_date": next(iter(overview_dates), None),
        "weight_dates": weight_dates,
        "labels": dict(sorted(labels.items())),
        "topic_file_count": len(topic_files),
        "fresh_component_count": fresh_component_count,
        "stale_component_count": stale_component_count,
    }
    return issues, metrics


def _write_summary(
    *,
    summary_path: Path,
    run_id: str,
    end_date: str,
    started_at: datetime,
    status: str,
    returncode: int,
    issues: list[str],
    metrics: dict[str, Any],
    log_path: Path,
) -> None:
    payload = {
        "run_id": run_id,
        "end_date": end_date,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now().isoformat(),
        "status": status,
        "returncode": returncode,
        "issues": issues,
        "metrics": metrics,
        "stdout_path": str(log_path),
    }
    summary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    args = _build_parser().parse_args()
    end_date = _validate_date(args.end_date)
    run_id = args.run_id or (
        f"{args.trigger_type}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    )
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    log_path = SUMMARY_DIR / f"{run_id}.log"
    summary_path = SUMMARY_DIR / f"{run_id}.json"
    started_at = datetime.now()

    if not args.validate_only and not args.allow_non_trade_day:
        if not _is_trade_day(end_date):
            log_path.write_text(
                f"skip_non_trade_day={end_date}\n",
                encoding="utf-8",
            )
            _write_summary(
                summary_path=summary_path,
                run_id=run_id,
                end_date=end_date,
                started_at=started_at,
                status="skipped",
                returncode=0,
                issues=[],
                metrics={"is_trade_day": False},
                log_path=log_path,
            )
            print(f"run_id={run_id}")
            print("status=skipped")
            print("issues_count=0")
            print(f"summary_json={summary_path}")
            return

    returncode = 0 if args.validate_only else _run_generator(end_date, log_path)
    if args.validate_only:
        log_path.write_text("validate_only=true\n", encoding="utf-8")

    issues: list[str] = []
    metrics: dict[str, Any] = {}
    if returncode:
        issues.append("ETF constituent data generator exited with a non-zero code.")
    else:
        issues, metrics = _validate_outputs(end_date)

    status = "success" if returncode == 0 and not issues else "failed"
    _write_summary(
        summary_path=summary_path,
        run_id=run_id,
        end_date=end_date,
        started_at=started_at,
        status=status,
        returncode=returncode,
        issues=issues,
        metrics=metrics,
        log_path=log_path,
    )

    print(f"run_id={run_id}")
    print(f"status={status}")
    print(f"issues_count={len(issues)}")
    print(f"target_count={metrics.get('target_count', 0)}")
    print(f"latest_date={metrics.get('latest_date', '')}")
    print(
        "labels="
        + json.dumps(metrics.get("labels", {}), ensure_ascii=False, sort_keys=True)
    )
    print(f"summary_json={summary_path}")
    print(f"stdout_log={log_path}")
    for issue in issues:
        print(f"issue={issue}")

    if status == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

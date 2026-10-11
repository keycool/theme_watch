from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from backtest_etf_watch import (
    CORE_BENCHMARK,
    DATA_DIR,
    DEFAULT_END_DATE,
    HORIZONS,
    OUTPUT_DIR,
    TargetSpec,
    _json_default,
    add_forward_outcomes,
    add_indicators,
    build_core_target_history,
    build_lifecycle_series,
    build_snapshot_map,
    extract_events,
    load_index_weights,
    load_market_amount,
    load_tushare_daily,
    prepare_component_frame,
    summarize_event_rows,
    validate_lifecycle_replay,
)
from backtest_execution_discipline import (
    ExecutionVariant,
    simulate_execution_discipline,
)


ROOT = Path(__file__).resolve().parent
EXPANDED_OUTPUT_DIR = ROOT / "backtest_results"
EXPANDED_CACHE_DIR = DATA_DIR / "backtest_cache" / "expanded_metadata"
CORE_TARGETS_PATH = ROOT / "targets.json"


@dataclass(frozen=True)
class ExpandedSpec:
    index_code: str
    index_name: str
    category: str
    index_list_date: str | None
    execution_code: str | None
    execution_list_date: str | None
    execution_delist_date: str | None
    execution_status: str | None
    execution_count: int
    current_target: bool


def _date_number(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).replace("-", "")
    if text.endswith(".0"):
        text = text[:-2]
    return int(text) if text.isdigit() else None


def _date_text(value: Any) -> str | None:
    number = _date_number(value)
    return str(number) if number is not None else None


def _read_current_index_codes(etf_basic: pd.DataFrame) -> set[str]:
    targets = json.loads(CORE_TARGETS_PATH.read_text(encoding="utf-8"))
    etf_map = {
        str(row["ts_code"]): str(row["index_code"])
        for _, row in etf_basic.dropna(subset=["ts_code", "index_code"]).iterrows()
    }
    current: set[str] = set()
    for target in targets:
        code = str(target["code"])
        if str(target.get("kind")) == "index":
            current.add(code)
        elif code in etf_map:
            current.add(etf_map[code])
    return current


def build_expanded_pool(pro: Any, end_date: str, max_indexes: int) -> list[ExpandedSpec]:
    cache = EXPANDED_CACHE_DIR / f"pool_metadata_v5_{end_date}.json"
    if cache.exists():
        raw = json.loads(cache.read_text(encoding="utf-8"))
        return [ExpandedSpec(**item) for item in raw]

    etf_parts = [pro.etf_basic(list_status=status) for status in ("L", "D", "P")]
    etf = pd.concat(etf_parts, ignore_index=True)
    try:
        fund = pro.fund_basic(market="E")
        fund = fund[["ts_code", "delist_date"]].drop_duplicates("ts_code", keep="last")
        etf = etf.merge(fund, on="ts_code", how="left")
    except Exception:
        etf["delist_date"] = None
    etf["list_date_num"] = etf["list_date"].map(_date_number)
    etf = (
        etf.sort_values(["ts_code", "list_date_num"], na_position="last")
        .drop_duplicates("ts_code", keep="first")
    )
    etf = etf[
        etf["index_code"].notna()
        & etf["list_date_num"].notna()
        & (etf["list_date_num"] <= int(end_date))
    ].copy()
    index = pro.index_basic()
    current_codes = _read_current_index_codes(etf)
    index["index_list_date_num"] = index["list_date"].map(_date_number)
    index = index[
        (
            index["category"].isin(["行业指数", "主题指数"])
            & index["ts_code"].astype(str).str.endswith((".CSI", ".SH", ".SZ"))
        )
        | index["ts_code"].astype(str).isin(current_codes)
    ].copy()
    index_for_merge = index[["ts_code", "name", "category", "list_date"]].rename(
        columns={
            "ts_code": "index_code_key",
            "name": "research_index_name",
            "category": "research_category",
            "list_date": "research_index_list_date",
        }
    )
    eligible = etf.merge(
        index_for_merge,
        left_on="index_code",
        right_on="index_code_key",
        how="inner",
    )
    candidates: list[ExpandedSpec] = []
    for (index_code, index_name, category), group in eligible.groupby(
        ["index_code", "research_index_name", "research_category"], dropna=False
    ):
        group = group.sort_values(["list_date_num", "ts_code"])
        first = group.iloc[0]
        candidates.append(
            ExpandedSpec(
                index_code=str(index_code),
                index_name=str(index_name),
                category=str(category),
                index_list_date=_date_text(first["research_index_list_date"]),
                execution_code=str(first["ts_code"]),
                execution_list_date=_date_text(first["list_date_num"]),
                execution_delist_date=_date_text(first.get("delist_date")),
                execution_status=str(first.get("list_status")) if pd.notna(first.get("list_status")) else None,
                execution_count=int(len(group)),
                current_target=str(index_code) in current_codes,
            )
        )
    selected_codes = {item.index_code for item in candidates}
    for index_code in sorted(current_codes - selected_codes):
        group = etf[etf["index_code"].astype(str) == index_code].sort_values(
            ["list_date_num", "ts_code"]
        )
        if group.empty:
            continue
        first = group.iloc[0]
        candidates.append(
            ExpandedSpec(
                index_code=index_code,
                index_name=str(first.get("index_name") or index_code),
                category="production_current",
                index_list_date=None,
                execution_code=str(first["ts_code"]),
                execution_list_date=_date_text(first["list_date_num"]),
                execution_delist_date=_date_text(first.get("delist_date")),
                execution_status=str(first.get("list_status")) if pd.notna(first.get("list_status")) else None,
                execution_count=int(len(group)),
                current_target=True,
            )
        )
    candidates.sort(
        key=lambda item: (
            not item.current_target,
            _date_number(item.execution_list_date) or 99999999,
            item.index_code,
        )
    )
    selected = candidates[:max_indexes]
    if not current_codes.issubset({item.index_code for item in selected}):
        missing = sorted(current_codes - {item.index_code for item in selected})
        raise RuntimeError(f"Expanded pool cap excludes current targets: {missing}")
    EXPANDED_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(
        json.dumps([asdict(item) for item in selected], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return selected


def _minimal_lifecycle_history(spec: ExpandedSpec, price: pd.DataFrame) -> pd.DataFrame:
    prepared = add_indicators(price)
    lifecycle = build_lifecycle_series(prepared)
    history = prepared.merge(lifecycle, on="trade_date", how="left")
    history["code"] = spec.index_code
    history["name"] = spec.index_name
    history["engine"] = "expanded_index_lifecycle"
    history["history_ready"] = history.index.to_series() + 1 >= 750
    history["entry_guard_passed"] = history["history_ready"]
    history["funding_min3"] = None
    history["breakout_pass"] = False
    history["leader_pass"] = False
    history["trend_confirmed_today"] = history["trend_confirmed_today"].fillna(False)
    history["trend_confirmed_active"] = history["trend_confirmed_active"].fillna(False)
    history["initial_start_today"] = history["initial_start_today"].fillna(False)
    return history


def _wave_id(events: list[dict[str, Any]], max_gap_days: int = 10) -> list[dict[str, Any]]:
    if not events:
        return []
    ordered = sorted(events, key=lambda item: (item["signalDate"], item["code"]))
    wave = 0
    previous = None
    result = []
    for event in ordered:
        current = datetime.strptime(event["signalDate"], "%Y%m%d")
        if previous is not None and (current - previous).days > max_gap_days:
            wave += 1
        row = dict(event)
        row["waveId"] = wave
        result.append(row)
        previous = current
    return result


def _wave_summary(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = _wave_id(events)
    grouped: list[dict[str, Any]] = []
    for wave_id, frame in pd.DataFrame(rows).groupby("waveId") if rows else []:
        values = pd.to_numeric(frame.get("d20ExcessReturnPct"), errors="coerce").dropna()
        grouped.append(
            {
                "waveId": int(wave_id),
                "startDate": str(frame["signalDate"].min()),
                "endDate": str(frame["signalDate"].max()),
                "eventCount": int(len(frame)),
                "targetCount": int(frame["code"].nunique()),
                "meanD20ExcessReturnPct": float(values.mean()) if not values.empty else None,
                "medianD20ExcessReturnPct": float(values.median()) if not values.empty else None,
                "positiveD20ExcessRatePct": float((values > 0).mean() * 100) if not values.empty else None,
            }
        )
    return grouped


def _write_expanded_report(
    path: Path,
    meta: dict[str, Any],
    signal_summaries: list[dict[str, Any]],
    wave_summary: list[dict[str, Any]],
    complete_summaries: list[dict[str, Any]],
    execution_summaries: list[dict[str, Any]],
) -> None:
    def row(event_type: str, period: str = "full") -> dict[str, Any] | None:
        return next(
            (item for item in signal_summaries if item["eventType"] == event_type and item["period"] == period and item["horizonTradeDays"] == 20),
            None,
        )

    lines = [
        "# ETF Watch 扩大样本回测",
        "",
        f"- 生成时间：{meta['generatedAt']}",
        f"- 指数信号区间：{meta['startDate']}—{meta['endDate']}",
        f"- 唯一行业/主题指数：{meta['poolCount']} 个；完整三阶段子池：{meta['completePoolCount']} 个",
        "- 当前生产25目标未被修改；本报告是离线研究产物。",
        "",
        "## 一、三层样本规模",
        "",
        f"- 指数生命周期层：{meta['lifecycleEventCount']} 个初始启动事件。",
        f"- 市场波次层：{meta['waveCount']} 个波次；同一市场波次内10个自然日以内的事件合并观察。",
        f"- 完整策略层：{meta['completeEventCount']} 个事件，使用历史权重和成分股日线。",
        f"- ETF执行层：{meta['executionTargetCount']} 个有代表性ETF历史价格；只从实际上市后计算下一日开盘。",
        "",
        "## 二、生命周期信号层（20日）",
        "",
        "| 信号 | 样本 | 平均超额 | 超额胜率 | 非重叠超额 | 次日开盘收益 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for event_type in ["lifecycle_initial_start", "lifecycle_trend_confirmation"]:
        item = row(event_type)
        if item:
            lines.append(
                f"| {event_type} | {item['completedCount']} | {item['meanExcessReturnPct'] or '-'}% | "
                f"{item['positiveExcessRatePct'] or '-'}% | {item['nonOverlapMeanExcessPct'] or '-'}% | "
                f"{item['meanNextOpenReturnPct'] or '-'}% |"
            )
    lines.extend([
        "",
        "## 三、市场波次层",
        "",
        "| 波次 | 日期 | 事件数 | 标的数 | 平均20日超额 | 超额为正比例 |",
        "|---:|---|---:|---:|---:|---:|",
    ])
    for item in wave_summary:
        lines.append(
            f"| {item['waveId']} | {item['startDate']}—{item['endDate']} | {item['eventCount']} | "
            f"{item['targetCount']} | {item['meanD20ExcessReturnPct'] or '-'}% | "
            f"{item['positiveD20ExcessRatePct'] or '-'}% |"
        )
    lines.extend([
        "",
        "## 四、完整三阶段子池",
        "",
        "| 信号 | 样本 | 平均超额 | 超额胜率 | 非重叠超额 |",
        "|---|---:|---:|---:|---:|",
    ])
    for item in complete_summaries:
        if item.get("period") == "full" and item.get("horizonTradeDays") == 20:
            lines.append(
                f"| {item['eventType']} | {item['completedCount']} | {item['meanExcessReturnPct'] or '-'}% | "
                f"{item['positiveExcessRatePct'] or '-'}% | {item['nonOverlapMeanExcessPct'] or '-'}% |"
            )
    lines.extend([
        "",
        "## 五、ETF执行层",
        "",
        "| 纪律 | 最大槽位 | 交易数 | 年化收益 | 最大回撤 | 胜率 |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for item in execution_summaries:
        if item["variant"] == "fixed_20_only" and item["costBpsPerSide"] == 10.0:
            lines.append(
                f"| {item['variant']} | {item['maxPositions']} | {item['tradeCount']} | "
                f"{item['activePeriodAnnualizedReturnPct']:.2f}% | {item['maxDrawdownPct']:.2f}% | "
                f"{item['tradeWinRatePct'] or '-'}% |"
            )
    lines.extend([
        "",
        "## 六、严格限制",
        "",
        "- 扩展池按ETF元数据和指数类别预先定义，不按历史收益筛选；仍不能代表全部历史可投资指数。",
        "- 指数信号层可以早于ETF上市；ETF执行层只接受实际存在的下一交易日开盘。",
        "- 完整策略子池才使用历史权重、资金和成分股事件；生命周期执行层不是完整三条件策略。",
        "- 事件之间存在行业相关性，波次统计比原始交易数更接近独立样本。",
        "- 本回测没有改写生产参数，也不构成自动下单授权。",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_expanded_execution_grid(
    histories: dict[str, pd.DataFrame],
    execution_prices: dict[str, pd.DataFrame | None],
    specs: dict[str, TargetSpec],
    market_dates: list[str],
    benchmark: pd.DataFrame,
    output_dir: Path,
    start_date: str,
    end_date: str,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    variant = ExecutionVariant("fixed_20_only", False, fixed_holding_days=20)
    summaries: list[dict[str, Any]] = []
    default_trades: list[dict[str, Any]] = []
    default_nav: list[dict[str, Any]] = []
    for max_positions in (1, 2, 3):
        result = simulate_execution_discipline(
            histories,
            execution_prices,
            specs,
            market_dates,
            benchmark,
            variant,
            max_positions=max_positions,
            cost_bps_per_side=10.0,
        )
        summaries.append(result["summary"])
        if max_positions == 2:
            default_trades = [{"variant": variant.name, **row} for row in result["trades"]]
            default_nav = [{"variant": variant.name, **row} for row in result["nav"]]
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"etf_watch_expanded_execution_{start_date}_{end_date}"
    json_path = output_dir / f"{stem}.json"
    summary_path = output_dir / f"{stem}_summary.csv"
    trades_path = output_dir / f"{stem}_trades.csv"
    nav_path = output_dir / f"{stem}_nav.csv"
    payload = {
        "meta": {
            "schemaVersion": "1.0",
            "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "startDate": start_date,
            "endDate": end_date,
            "entryRule": "expanded lifecycle initial_start_today and 750-trade-day history guard; next ETF open",
            "variantScope": "fixed_20_only; max positions 1, 2, 3; 10bp per side",
            "signalUsesFutureRows": False,
            "fullThreeStageGuard": False,
        },
        "summaries": summaries,
        "defaultTrades": default_trades,
        "defaultNav": default_nav,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(summaries).to_csv(summary_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(default_trades).to_csv(trades_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(default_nav).to_csv(nav_path, index=False, encoding="utf-8-sig")
    report_path = output_dir / f"{stem}.md"
    lines = [
        "# ETF Watch 扩展池执行层回测",
        "",
        f"- 区间：{start_date}—{end_date}",
        "- 入场：严格生命周期初始启动，下一交易日代表ETF开盘；持有20个ETF交易日。",
        "- 本层是生命周期执行层，不包含完整三阶段资金/龙头门槛；完整三阶段另列。",
        "",
        "| 最大槽位 | 交易数 | 年化收益 | 最大回撤 | Sharpe | 胜率 | 平均利用率 |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in summaries:
        lines.append(
            f"| {item['maxPositions']} | {item['tradeCount']} | {item['activePeriodAnnualizedReturnPct']:.2f}% | "
            f"{item['maxDrawdownPct']:.2f}% | {item['sharpeZeroRate'] or '-'} | "
            f"{item['tradeWinRatePct'] or '-'}% | {item['averageUtilizationPct']:.2f}% |"
        )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summaries, {
        "json": str(json_path),
        "summaryCsv": str(summary_path),
        "tradesCsv": str(trades_path),
        "navCsv": str(nav_path),
        "report": str(report_path),
    }


def run_research(
    start_date: str,
    end_date: str,
    output_dir: Path,
    *,
    max_indexes: int = 80,
    complete_count: int = 40,
) -> dict[str, Any]:
    if not os.environ.get("TUSHARE_TOKEN"):
        raise RuntimeError("TUSHARE_TOKEN is required.")
    import tushare as ts

    pro = ts.pro_api(os.environ["TUSHARE_TOKEN"])
    pool = build_expanded_pool(pro, end_date, max_indexes)
    print(f"expanded_pool={len(pool)} complete_pool={min(complete_count, len(pool))}", flush=True)
    benchmark = load_tushare_daily(pro, "index_daily", CORE_BENCHMARK, start_date, end_date)
    market_dates = benchmark["trade_date"].astype(str).tolist()

    signal_prices: dict[str, pd.DataFrame] = {}
    execution_prices: dict[str, pd.DataFrame | None] = {}
    histories: dict[str, pd.DataFrame] = {}
    specs: dict[str, TargetSpec] = {}
    signal_events: list[dict[str, Any]] = []
    for offset, spec in enumerate(pool, start=1):
        price = load_tushare_daily(pro, "index_daily", spec.index_code, start_date, end_date)
        if price.empty or len(price) < 750:
            print(f"skip_short_index={spec.index_code} rows={len(price)}", flush=True)
            continue
        signal_prices[spec.index_code] = price
        execution = None
        if spec.execution_code:
            execution = load_tushare_daily(pro, "fund_daily", spec.execution_code, start_date, end_date)
        execution_prices[spec.index_code] = execution
        specs[spec.index_code] = TargetSpec(
            code=spec.index_code,
            name=spec.index_name,
            kind="index",
            engine="core",
            price_code=spec.index_code,
            execution_code=spec.execution_code,
            benchmark_code=CORE_BENCHMARK,
        )
        history = _minimal_lifecycle_history(spec, price)
        histories[spec.index_code] = history
        for event in extract_events(history):
            if event["eventType"] != "lifecycle_initial_start":
                continue
            signal_events.append(
                add_forward_outcomes(
                    event,
                    price,
                    benchmark,
                    execution,
                )
            )
        print(f"signal_target={offset}/{len(pool)} code={spec.index_code} rows={len(history)}", flush=True)

    lifecycle_summaries = summarize_event_rows(signal_events)
    waves = _wave_summary(signal_events)

    complete_pool = pool[: min(complete_count, len(pool))]
    complete_specs = {item.index_code: specs[item.index_code] for item in complete_pool if item.index_code in specs}
    complete_prices = {code: signal_prices[code] for code in complete_specs}
    complete_execution = {code: execution_prices.get(code) for code in complete_specs}
    weight_frames: dict[str, pd.DataFrame] = {}
    snapshots: dict[str, list[dict[str, Any]]] = {}
    for offset, spec in enumerate(complete_specs.values(), start=1):
        weights = load_index_weights(pro, spec.price_code, "20190101", end_date)
        weight_frames[spec.code] = weights
        snapshots[spec.code] = build_snapshot_map(weights)
        print(f"weight_target={offset}/{len(complete_specs)} code={spec.code}", flush=True)

    amount_dates = [date for date in market_dates if date >= "20190101"]
    market_amount = load_market_amount(pro, amount_dates, "20190101", end_date)
    component_codes: set[str] = set()
    for code, snapshot_rows in snapshots.items():
        for snapshot in snapshot_rows:
            for item in snapshot["core"] + snapshot["topTen"]:
                code_value = str(item["con_code"])
                if not code_value.endswith(".HK"):
                    component_codes.add(code_value)
    components: dict[str, pd.DataFrame] = {}
    for offset, code in enumerate(sorted(component_codes), start=1):
        frame = load_tushare_daily(pro, "daily", code, "20190101", end_date)
        if not frame.empty:
            components[code] = prepare_component_frame(frame)
        if offset % 50 == 0 or offset == len(component_codes):
            print(f"complete_components={offset}/{len(component_codes)}", flush=True)

    complete_histories: dict[str, pd.DataFrame] = {}
    complete_events: list[dict[str, Any]] = []
    for offset, code in enumerate(complete_specs, start=1):
        history = build_core_target_history(
            complete_specs[code],
            complete_prices[code],
            benchmark,
            market_amount,
            snapshots.get(code, []),
            components,
        )
        validate_lifecycle_replay(complete_prices[code], history, code)
        complete_histories[code] = history
        for event in extract_events(history):
            if event["eventType"] in {"lifecycle_initial_start", "label_启动确认", "allocation_starter", "allocation_confirmed"}:
                complete_events.append(
                    add_forward_outcomes(
                        event,
                        complete_prices[code],
                        benchmark,
                        complete_execution.get(code),
                    )
                )
        print(f"complete_target={offset}/{len(complete_specs)} code={code}", flush=True)

    complete_summaries = summarize_event_rows(complete_events)
    execution_summaries, execution_paths = run_expanded_execution_grid(
        histories,
        execution_prices,
        specs,
        market_dates,
        benchmark,
        output_dir,
        start_date,
        end_date,
    )

    meta = {
        "schemaVersion": "1.0",
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "startDate": start_date,
        "endDate": end_date,
        "poolCount": len(pool),
        "currentTargetCount": sum(item.current_target for item in pool),
        "loadedSignalTargetCount": len(histories),
        "completePoolCount": len(complete_specs),
        "completeLayerDataStartDate": "20190101",
        "lifecycleEventCount": len(signal_events),
        "waveCount": len(waves),
        "completeEventCount": len(complete_events),
        "executionTargetCount": sum(value is not None and not value.empty for value in execution_prices.values()),
        "lookaheadAllowed": False,
        "poolSelection": "ETF-backed domestic industry/theme indexes from L/D/P ETF metadata; current targets prioritized; no return-based selection",
        "etfMetadataStatuses": ["L", "D", "P"],
        "historicalEtfExecutionPointInTime": True,
    }
    result = {
        "meta": meta,
        "pool": [asdict(item) for item in pool],
        "signalSummaries": lifecycle_summaries,
        "waveSummary": waves,
        "completeSummaries": complete_summaries,
        "executionSummaries": execution_summaries,
        "limitations": [
            "The expanded pool is ETF-backed and category-filtered, not the complete historical index universe.",
            "The complete strategy layer is limited to the configured complete pool size.",
            "The expanded execution layer uses lifecycle-only entry guards; the complete strategy layer remains separately reported.",
            "Signal and ETF execution samples have different start dates because ETFs list after their indexes.",
        ],
        "executionPaths": {key: str(value) for key, value in execution_paths.items()},
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"etf_watch_expanded_{start_date}_{end_date}"
    json_path = output_dir / f"{stem}.json"
    events_path = output_dir / f"{stem}_lifecycle_events.csv"
    waves_path = output_dir / f"{stem}_waves.csv"
    report_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    pd.DataFrame(signal_events).to_csv(events_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(waves).to_csv(waves_path, index=False, encoding="utf-8-sig")
    _write_expanded_report(report_path, meta, lifecycle_summaries, waves, complete_summaries, execution_summaries)
    for key, path in {"json": json_path, "events": events_path, "waves": waves_path, "report": report_path}.items():
        print(f"expanded_{key}={path}", flush=True)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Expanded offline ETF Watch research backtest.")
    parser.add_argument("--start-date", default="20120101")
    parser.add_argument("--end-date", default=DEFAULT_END_DATE)
    parser.add_argument("--output-dir", type=Path, default=EXPANDED_OUTPUT_DIR)
    parser.add_argument("--max-indexes", type=int, default=80)
    parser.add_argument("--complete-count", type=int, default=40)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.start_date > args.end_date:
        raise ValueError("start_date must not be after end_date")
    run_research(
        args.start_date,
        args.end_date,
        args.output_dir,
        max_indexes=args.max_indexes,
        complete_count=args.complete_count,
    )


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class ExecutionVariant:
    name: str
    exit_below_ma60: bool
    fixed_holding_days: int | None = None
    unvalidated_holding_days: int | None = None


VARIANTS = (
    ExecutionVariant("fixed_20_only", False, fixed_holding_days=20),
    ExecutionVariant("ma60_exit_only", True),
    ExecutionVariant("fixed_20_or_ma60", True, fixed_holding_days=20),
    ExecutionVariant(
        "unvalidated_20_or_ma60", True, unvalidated_holding_days=20
    ),
)


def _rows_by_date(frame: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if frame is None or frame.empty:
        return {}
    ordered = frame.copy()
    ordered["trade_date"] = ordered["trade_date"].astype(str).str.replace("-", "")
    return {
        str(row["trade_date"]): row.to_dict()
        for _, row in ordered.sort_values("trade_date").iterrows()
    }


def _finite_number(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _max_drawdown(nav: pd.Series) -> float:
    if nav.empty:
        return 0.0
    drawdown = nav / nav.cummax() - 1
    return float(drawdown.min() * 100)


def _close_trade(
    position: dict[str, Any],
    exit_date: str,
    exit_price: float,
    exit_reason: str,
    cost_rate: float,
) -> tuple[float, dict[str, Any]]:
    proceeds = float(position["shares"]) * exit_price * (1 - cost_rate)
    trade = {
        "code": position["code"],
        "name": position["name"],
        "signalDate": position["signalDate"],
        "entryDate": position["entryDate"],
        "entryPrice": position["entryPrice"],
        "exitDate": exit_date,
        "exitPrice": exit_price,
        "exitReason": exit_reason,
        "holdingTradeDays": position["holdingTradeDays"],
        "breakoutValidated": position["breakoutValidated"],
        "trendConfirmed": position["trendConfirmed"],
        "leaderConfirmed": position["leaderConfirmed"],
        "returnPct": (proceeds / float(position["entryNotional"]) - 1) * 100,
        "maxAdversePct": position["maxAdversePct"],
        "maxFavorablePct": position["maxFavorablePct"],
    }
    return proceeds, trade


def simulate_execution_discipline(
    histories: dict[str, pd.DataFrame],
    execution_prices: dict[str, pd.DataFrame | None],
    specs: dict[str, Any],
    market_dates: list[str],
    benchmark: pd.DataFrame,
    variant: ExecutionVariant,
    *,
    max_positions: int = 2,
    cost_bps_per_side: float = 10.0,
) -> dict[str, Any]:
    if max_positions <= 0:
        raise ValueError("max_positions must be positive")
    dates = sorted({str(value) for value in market_dates})
    next_date = {dates[index]: dates[index + 1] for index in range(len(dates) - 1)}
    history_rows = {code: _rows_by_date(frame) for code, frame in histories.items()}
    execution_rows = {
        code: _rows_by_date(frame)
        for code, frame in execution_prices.items()
        if frame is not None
    }
    executable_codes = {
        code
        for code, spec in specs.items()
        if getattr(spec, "execution_code", None) and execution_rows.get(code)
    }
    cost_rate = cost_bps_per_side / 10_000
    cash = 1.0
    positions: dict[str, dict[str, Any]] = {}
    pending_entries: dict[str, list[dict[str, Any]]] = {}
    pending_exits: dict[str, str] = {}
    trades: list[dict[str, Any]] = []
    nav_rows: list[dict[str, Any]] = []
    last_close: dict[str, float] = {}
    counters = {
        "initialSignals": 0,
        "guardRejected": 0,
        "nonExecutableRejected": 0,
        "capacityRejected": 0,
        "alreadyHeldRejected": 0,
        "missingNextOpenRejected": 0,
    }
    first_entry_date: str | None = None

    for trade_date in dates:
        for code in list(pending_exits):
            execution_row = execution_rows.get(code, {}).get(trade_date)
            open_price = _finite_number(execution_row.get("open")) if execution_row else None
            if open_price is None or open_price <= 0:
                continue
            proceeds, trade = _close_trade(
                positions[code], trade_date, open_price, pending_exits[code], cost_rate
            )
            cash += proceeds
            trades.append(trade)
            del positions[code]
            del pending_exits[code]

        candidates = pending_entries.pop(trade_date, [])
        candidates.sort(
            key=lambda item: (
                not item["breakoutPassed"],
                -item["fundingScore"],
                item["order"],
            )
        )
        slots = max_positions - len(positions)
        accepted = candidates[: max(0, slots)]
        counters["capacityRejected"] += max(0, len(candidates) - len(accepted))
        nav_at_open = cash
        for code, position in positions.items():
            row = execution_rows[code].get(trade_date)
            price = _finite_number(row.get("open")) if row else last_close.get(code)
            if price is not None:
                nav_at_open += float(position["shares"]) * price
        slot_value = nav_at_open / max_positions
        for signal in accepted:
            code = signal["code"]
            if code in positions:
                counters["alreadyHeldRejected"] += 1
                continue
            execution_row = execution_rows[code].get(trade_date)
            open_price = _finite_number(execution_row.get("open")) if execution_row else None
            if open_price is None or open_price <= 0:
                counters["missingNextOpenRejected"] += 1
                continue
            allocation = min(cash, slot_value)
            if allocation <= 0:
                counters["capacityRejected"] += 1
                continue
            shares = allocation * (1 - cost_rate) / open_price
            cash -= allocation
            positions[code] = {
                "code": code,
                "name": signal["name"],
                "signalDate": signal["signalDate"],
                "entryDate": trade_date,
                "entryPrice": open_price,
                "entryNotional": allocation,
                "shares": shares,
                "holdingTradeDays": 0,
                "breakoutValidated": bool(signal["breakoutPassed"]),
                "trendConfirmed": False,
                "leaderConfirmed": False,
                "maxAdversePct": 0.0,
                "maxFavorablePct": 0.0,
            }
            first_entry_date = first_entry_date or trade_date

        invested_value = 0.0
        for code, position in positions.items():
            execution_row = execution_rows[code].get(trade_date)
            close_price = _finite_number(execution_row.get("close")) if execution_row else None
            if close_price is None:
                close_price = last_close.get(code)
            if close_price is None:
                continue
            last_close[code] = close_price
            market_value = float(position["shares"]) * close_price
            invested_value += market_value
            mark_return = market_value / float(position["entryNotional"]) - 1
            position["maxAdversePct"] = min(
                float(position["maxAdversePct"]), mark_return * 100
            )
            position["maxFavorablePct"] = max(
                float(position["maxFavorablePct"]), mark_return * 100
            )
            position["holdingTradeDays"] += 1
            history_row = history_rows.get(code, {}).get(trade_date)
            if history_row:
                position["breakoutValidated"] = bool(
                    position["breakoutValidated"] or history_row.get("breakout_pass")
                )
                position["trendConfirmed"] = bool(
                    position["trendConfirmed"]
                    or history_row.get("trend_confirmed_today")
                    or history_row.get("trend_confirmed_active")
                )
                position["leaderConfirmed"] = bool(
                    position["leaderConfirmed"] or history_row.get("leader_pass")
                )
                close = _finite_number(history_row.get("close"))
                ma60 = _finite_number(history_row.get("ma60"))
                below_ma60 = bool(
                    close is not None and ma60 is not None and close < ma60
                )
            else:
                below_ma60 = False
            days_held = int(position["holdingTradeDays"])
            reason = None
            if variant.exit_below_ma60 and below_ma60:
                reason = "close_below_ma60"
            elif variant.fixed_holding_days and days_held >= variant.fixed_holding_days:
                reason = "fixed_holding_period"
            elif (
                variant.unvalidated_holding_days
                and days_held >= variant.unvalidated_holding_days
                and not position["breakoutValidated"]
            ):
                reason = "unvalidated_timeout"
            if reason and code not in pending_exits:
                pending_exits[code] = reason

        nav = cash + invested_value
        nav_rows.append(
            {
                "tradeDate": trade_date,
                "nav": nav,
                "cash": cash,
                "invested": invested_value,
                "utilizationPct": invested_value / nav * 100 if nav else 0.0,
                "positionCount": len(positions),
            }
        )

        for code in executable_codes:
            history_row = history_rows.get(code, {}).get(trade_date)
            if not history_row or not bool(history_row.get("initial_start_today")):
                continue
            counters["initialSignals"] += 1
            if not bool(history_row.get("entry_guard_passed")):
                counters["guardRejected"] += 1
                continue
            if code in positions or code in pending_exits:
                counters["alreadyHeldRejected"] += 1
                continue
            entry_date = next_date.get(trade_date)
            if entry_date is None:
                counters["missingNextOpenRejected"] += 1
                continue
            funding = _finite_number(history_row.get("funding_min3")) or 0.0
            pending_entries.setdefault(entry_date, []).append(
                {
                    "code": code,
                    "name": str(history_row.get("name") or code),
                    "signalDate": trade_date,
                    "breakoutPassed": bool(history_row.get("breakout_pass")),
                    "fundingScore": funding,
                    "order": list(specs).index(code),
                }
            )

    if dates and positions:
        final_date = dates[-1]
        for code in list(positions):
            close_price = last_close.get(code)
            if close_price is None:
                continue
            proceeds, trade = _close_trade(
                positions[code], final_date, close_price, "end_of_test", cost_rate
            )
            cash += proceeds
            trades.append(trade)
            del positions[code]
        nav_rows[-1].update(
            {"nav": cash, "cash": cash, "invested": 0.0, "utilizationPct": 0.0, "positionCount": 0}
        )

    nav_frame = pd.DataFrame(nav_rows)
    if first_entry_date:
        first_entry_index = int(
            nav_frame.index[nav_frame["tradeDate"] >= first_entry_date][0]
        )
        active = nav_frame.iloc[max(0, first_entry_index - 1) :].reset_index(drop=True)
    else:
        active = nav_frame.iloc[0:0]
    daily_returns = active["nav"].pct_change().dropna() if not active.empty else pd.Series(dtype=float)
    trade_returns = [float(item["returnPct"]) for item in trades]
    benchmark_rows = _rows_by_date(benchmark)
    benchmark_return = None
    if first_entry_date and dates:
        start_candidates = [date for date in benchmark_rows if date >= first_entry_date]
        end_candidates = [date for date in benchmark_rows if date <= dates[-1]]
        if start_candidates and end_candidates:
            start_value = _finite_number(benchmark_rows[min(start_candidates)].get("close"))
            end_value = _finite_number(benchmark_rows[max(end_candidates)].get("close"))
            if start_value and end_value:
                benchmark_return = (end_value / start_value - 1) * 100
    active_days = max(1, len(active))
    total_return = (float(active.iloc[-1]["nav"]) / float(active.iloc[0]["nav"]) - 1) if len(active) > 1 else 0.0
    summary = {
        "variant": variant.name,
        "maxPositions": max_positions,
        "slotWeightPct": 100 / max_positions,
        "costBpsPerSide": cost_bps_per_side,
        "firstEntryDate": first_entry_date,
        "finalNav": float(nav_frame.iloc[-1]["nav"]) if not nav_frame.empty else 1.0,
        "activePeriodReturnPct": total_return * 100,
        "activePeriodAnnualizedReturnPct": ((1 + total_return) ** (252 / active_days) - 1) * 100,
        "maxDrawdownPct": _max_drawdown(active["nav"]) if not active.empty else 0.0,
        "annualizedVolatilityPct": float(daily_returns.std() * (252**0.5) * 100) if not daily_returns.empty else 0.0,
        "sharpeZeroRate": float(daily_returns.mean() / daily_returns.std() * (252**0.5)) if len(daily_returns) > 1 and daily_returns.std() else None,
        "averageUtilizationPct": float(active["utilizationPct"].mean()) if not active.empty else 0.0,
        "maximumConcurrentPositions": int(nav_frame["positionCount"].max()) if not nav_frame.empty else 0,
        "tradeCount": len(trades),
        "tradeWinRatePct": sum(value > 0 for value in trade_returns) / len(trade_returns) * 100 if trade_returns else None,
        "meanTradeReturnPct": sum(trade_returns) / len(trade_returns) if trade_returns else None,
        "medianTradeReturnPct": float(pd.Series(trade_returns).median()) if trade_returns else None,
        "meanHoldingTradeDays": sum(item["holdingTradeDays"] for item in trades) / len(trades) if trades else None,
        "breakoutValidatedTradePct": sum(bool(item["breakoutValidated"]) for item in trades) / len(trades) * 100 if trades else None,
        "benchmarkFullInvestmentReturnPct": benchmark_return,
        "exitReasonCounts": pd.Series([item["exitReason"] for item in trades]).value_counts().to_dict() if trades else {},
        **counters,
    }
    return {"summary": summary, "trades": trades, "nav": nav_rows}


def run_execution_grid(
    histories: dict[str, pd.DataFrame],
    execution_prices: dict[str, pd.DataFrame | None],
    specs: dict[str, Any],
    market_dates: list[str],
    benchmark: pd.DataFrame,
) -> dict[str, Any]:
    summaries: list[dict[str, Any]] = []
    default_trades: list[dict[str, Any]] = []
    default_nav: list[dict[str, Any]] = []
    for variant in VARIANTS:
        for max_positions in (1, 2, 3, 5):
            for cost_bps in (0.0, 5.0, 10.0):
                result = simulate_execution_discipline(
                    histories,
                    execution_prices,
                    specs,
                    market_dates,
                    benchmark,
                    variant,
                    max_positions=max_positions,
                    cost_bps_per_side=cost_bps,
                )
                summaries.append(result["summary"])
                if max_positions == 2 and cost_bps == 10.0:
                    default_trades.extend(
                        {"variant": variant.name, **row} for row in result["trades"]
                    )
                    default_nav.extend(
                        {"variant": variant.name, **row} for row in result["nav"]
                    )
    return {"summaries": summaries, "defaultTrades": default_trades, "defaultNav": default_nav}


def write_execution_outputs(
    output_dir: Path,
    start_date: str,
    end_date: str,
    result: dict[str, Any],
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"etf_watch_execution_backtest_{start_date}_{end_date}"
    json_path = output_dir / f"{stem}.json"
    summary_path = output_dir / f"{stem}_summary.csv"
    trades_path = output_dir / f"{stem}_trades.csv"
    nav_path = output_dir / f"{stem}_nav.csv"
    report_path = output_dir / f"{stem}.md"
    payload = {
        "meta": {
            "schemaVersion": "1.0",
            "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "startDate": start_date,
            "endDate": end_date,
            "entryRule": "initial_start_today and entry_guard_passed; execute next market open",
            "automaticScaling": False,
            "signalUsesFutureRows": False,
            "defaultCapacity": "maximum 2 positions, 50% satellite capacity per slot",
            "defaultCostBpsPerSide": 10.0,
        },
        **result,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(result["summaries"]).to_csv(summary_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(result["defaultTrades"]).to_csv(trades_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(result["defaultNav"]).to_csv(nav_path, index=False, encoding="utf-8-sig")
    default_rows = [
        row
        for row in result["summaries"]
        if row["maxPositions"] == 2 and row["costBpsPerSide"] == 10.0
    ]
    lines = [
        "# ETF Watch 极简执行纪律回测",
        "",
        f"- 区间：{start_date}—{end_date}",
        "- 默认组合：最多同时持有2个行业，每个槽位占卫星容量50%，单边成本10bp。",
        "- 入场：严格MA60初始启动当日收盘后确认，下一市场交易日ETF开盘执行。",
        "- 不因MA250或龙头确认自动加仓。",
        "",
        "## 默认组合结果",
        "",
        "| 纪律 | 交易数 | 年化收益 | 最大回撤 | 平均利用率 | 胜率 | 单笔均值 | 平均持有日 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in default_rows:
        lines.append(
            f"| {row['variant']} | {row['tradeCount']} | {row['activePeriodAnnualizedReturnPct']:.2f}% | "
            f"{row['maxDrawdownPct']:.2f}% | {row['averageUtilizationPct']:.2f}% | "
            f"{row['tradeWinRatePct']:.2f}% | {row['meanTradeReturnPct']:.2f}% | "
            f"{row['meanHoldingTradeDays']:.1f} |"
        )
    lines.extend(
        [
            "",
            "## 纪律定义",
            "",
            "- `fixed_20_only`：固定持有20个交易日。",
            "- `ma60_exit_only`：跟踪判断对象收盘跌破MA60后，下一市场交易日开盘退出。",
            "- `fixed_20_or_ma60`：20日到期或跌破MA60，先发生者退出。",
            "- `unvalidated_20_or_ma60`：20日内未出现带量突破则到期退出；已验证则继续持有，直到跌破MA60。",
            "",
            "本报告是离线账户模拟，不参与生产标签、资金接口或自动调参。",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "json": str(json_path),
        "summaryCsv": str(summary_path),
        "tradesCsv": str(trades_path),
        "navCsv": str(nav_path),
        "report": str(report_path),
    }

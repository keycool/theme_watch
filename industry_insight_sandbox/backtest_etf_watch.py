from __future__ import annotations

import argparse
from bisect import bisect_right
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from backtest_execution_discipline import run_execution_grid, write_execution_outputs

from generate_dashboard_data import (
    CORE_WEIGHT_COVERAGE,
    FUNDING_CONFIRM_PERCENTILE,
    LEADER_WATCH_COUNT,
    LOW_BELOW_MA250_5_PASS_DAYS,
    LOW_BELOW_MA250_5_WARNING_DAYS,
    LOW_DEEP_10_PASS_DAYS,
    LOW_DEEP_10_PASS_MIN_BELOW_DAYS,
    LOW_DEEP_10_WARNING_DAYS,
    LOW_DEEP_10_WARNING_MIN_BELOW_DAYS,
    MAX_CORE_COUNT,
    STRICT_LEADER_COUNT,
    limit_threshold,
)
from generate_hk_qdii_dashboard_data import (
    LEADER_ABSOLUTE_RETURN,
    LEADER_RETURN_PERCENTILE,
)
from moving_average_lifecycle import (
    CONVERGENCE_LOOKBACK_DAYS,
    CONVERGENCE_REQUIRED_DAYS,
    SEPARATION_LOOKBACK_DAYS,
    SEPARATION_MIN_DISTANCE,
    SEPARATION_MIN_OBSERVATIONS,
    SEPARATION_RANK_THRESHOLD,
    WARM_UP_LOOKBACK_DAYS,
    evaluate_moving_average_lifecycle,
)


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "backtest_cache"
PRODUCTION_CACHE_DIR = DATA_DIR / "cache"
OUTPUT_DIR = ROOT / "backtest_results"
OVERVIEW_PATH = DATA_DIR / "overview.json"

DEFAULT_START_DATE = "20190101"
DEFAULT_END_DATE = "20260813"
HORIZONS = (5, 20, 60)
PRIMARY_LABELS = ("观察中", "接近启动", "启动确认", "趋势延续")
CORE_BENCHMARK = "000300.SH"
HK_BENCHMARK = "HSI"
TENCENT_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"


@dataclass(frozen=True)
class TargetSpec:
    code: str
    name: str
    kind: str
    engine: str
    price_code: str
    execution_code: str | None
    benchmark_code: str


def safe_code(value: str) -> str:
    return value.replace(".", "_").replace("/", "_")


def normalize_daily(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    result = frame.copy()
    result["trade_date"] = result["trade_date"].astype(str).str.replace("-", "")
    numeric = ["open", "high", "low", "close", "pct_chg", "amount", "vol", "volume"]
    for column in numeric:
        if column in result:
            result[column] = pd.to_numeric(result[column], errors="coerce")
    if "pct_chg" not in result or result["pct_chg"].isna().all():
        result["pct_chg"] = result["close"].pct_change() * 100
    return (
        result.drop_duplicates("trade_date", keep="last")
        .sort_values("trade_date")
        .reset_index(drop=True)
    )


def add_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    result = normalize_daily(frame)
    result["ma20"] = result["close"].rolling(20).mean()
    result["ma60"] = result["close"].rolling(60).mean()
    result["ma250"] = result["close"].rolling(250).mean()
    result["ret5d"] = result["close"].pct_change(5) * 100
    result["ret20d"] = result["close"].pct_change(20) * 100
    result["return_p95"] = (
        result["pct_chg"]
        .rolling(120, min_periods=60)
        .quantile(LEADER_RETURN_PERCENTILE)
        .shift(1)
    )
    return result


def rolling_current_rank(series: pd.Series, window: int = 252, minimum: int = 120) -> pd.Series:
    return series.rolling(window, min_periods=minimum).rank(pct=True)


def _retry(fetcher: Callable[[], pd.DataFrame], label: str) -> pd.DataFrame:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            return fetcher()
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {label}: {last_error}") from last_error


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"trade_date": str})


def load_tushare_daily(
    pro: Any,
    endpoint: str,
    code: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    cache = CACHE_DIR / f"{endpoint}_{safe_code(code)}_{start_date}_{end_date}.csv"
    production_prefix = "stock_daily" if endpoint == "daily" else endpoint
    production = PRODUCTION_CACHE_DIR / f"{production_prefix}_{safe_code(code)}_{start_date}_{end_date}.csv"
    if cache.exists():
        return normalize_daily(_read_csv(cache))
    if production.exists():
        return normalize_daily(_read_csv(production))
    fields = "ts_code,trade_date,open,high,low,close,pct_chg,amount"
    frame = _retry(
        lambda: getattr(pro, endpoint)(
            ts_code=code,
            start_date=start_date,
            end_date=end_date,
            fields=fields,
        ),
        f"{endpoint}:{code}",
    )
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(cache, index=False, encoding="utf-8-sig")
    time.sleep(0.12)
    return normalize_daily(frame)


def load_index_weights(
    pro: Any,
    index_code: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    cache = CACHE_DIR / f"index_weight_{safe_code(index_code)}_{start_date}_{end_date}.csv"
    if cache.exists():
        frame = _read_csv(cache)
    else:
        parts: list[pd.DataFrame] = []
        start_year = int(start_date[:4])
        end_year = int(end_date[:4])
        for year in range(start_year, end_year + 1):
            segment_start = max(start_date, f"{year}0101")
            segment_end = min(end_date, f"{year}1231")
            part = _retry(
                lambda s=segment_start, e=segment_end: pro.index_weight(
                    index_code=index_code,
                    start_date=s,
                    end_date=e,
                ),
                f"index_weight:{index_code}:{year}",
            )
            if not part.empty:
                parts.append(part)
            time.sleep(0.12)
        frame = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        frame.to_csv(cache, index=False, encoding="utf-8-sig")
    if frame.empty:
        return frame
    frame["trade_date"] = frame["trade_date"].astype(str)
    frame["con_code"] = frame["con_code"].astype(str)
    frame["weight"] = pd.to_numeric(frame["weight"], errors="coerce")
    return (
        frame.dropna(subset=["trade_date", "con_code", "weight"])
        .drop_duplicates(["trade_date", "con_code"], keep="last")
        .sort_values(["trade_date", "weight"], ascending=[True, False])
        .reset_index(drop=True)
    )


def load_market_amount(
    pro: Any,
    trade_dates: list[str],
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    cache = CACHE_DIR / f"full_a_amount_{start_date}_{end_date}.csv"
    if cache.exists():
        existing = _read_csv(cache)
    else:
        seed = PRODUCTION_CACHE_DIR / "market_amount_history.csv"
        existing = _read_csv(seed) if seed.exists() else pd.DataFrame()
    amount_by_date = (
        existing.set_index("trade_date")["market_amount"].to_dict()
        if not existing.empty
        else {}
    )
    missing = [date for date in trade_dates if date not in amount_by_date]
    for offset, trade_date in enumerate(missing, start=1):
        daily = _retry(
            lambda d=trade_date: pro.daily(trade_date=d, fields="trade_date,amount"),
            f"full_a_amount:{trade_date}",
        )
        amount = pd.to_numeric(daily.get("amount"), errors="coerce").sum(min_count=1)
        if pd.isna(amount):
            raise RuntimeError(f"No full-A amount for {trade_date}.")
        amount_by_date[trade_date] = float(amount)
        if offset % 25 == 0 or offset == len(missing):
            checkpoint = pd.DataFrame(
                [
                    {"trade_date": date, "market_amount": amount_by_date[date]}
                    for date in trade_dates
                    if date in amount_by_date
                ]
            )
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            checkpoint.to_csv(cache, index=False, encoding="utf-8-sig")
            print(f"market_amount={offset}/{len(missing)}", flush=True)
        time.sleep(0.12)
    return pd.DataFrame(
        [
            {"trade_date": date, "market_amount": amount_by_date[date]}
            for date in trade_dates
            if date in amount_by_date
        ]
    )


def load_tencent_hk_daily(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    cache = CACHE_DIR / f"hk_daily_{safe_code(code)}_{start_date}_{end_date}.csv"
    if cache.exists():
        return normalize_daily(_read_csv(cache))
    bare = code.split(".")[0].zfill(5)
    quote_code = f"hk{bare}"
    request = Request(
        f"{TENCENT_KLINE_URL}?{urlencode({'param': f'{quote_code},day,,,2000,qfq'})}",
        headers={"User-Agent": "Mozilla/5.0 Industry-Insight/1.0"},
    )
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    rows = payload.get("data", {}).get(quote_code, {}).get("day", [])
    if not rows:
        raise RuntimeError(f"Tencent returned no HK history for {code}.")
    frame = pd.DataFrame(
        [
            {
                "trade_date": row[0],
                "open": row[1],
                "close": row[2],
                "high": row[3],
                "low": row[4],
                "volume": row[5],
            }
            for row in rows
        ]
    )
    frame = normalize_daily(frame)
    frame = frame[
        (frame["trade_date"] >= start_date) & (frame["trade_date"] <= end_date)
    ].copy()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(cache, index=False, encoding="utf-8-sig")
    time.sleep(0.08)
    return frame


def build_lifecycle_series(
    daily: pd.DataFrame,
    *,
    separation_min_distance: float = SEPARATION_MIN_DISTANCE,
    separation_rank_threshold: float = SEPARATION_RANK_THRESHOLD,
) -> pd.DataFrame:
    frame = daily[["trade_date", "close", "ma20", "ma60", "ma250"]].copy()
    frame = frame.sort_values("trade_date").reset_index(drop=True)
    count = len(frame)
    ma20_cross = [False] * count
    ma60_cross = [False] * count
    ma250_cross = [False] * count
    death_cross = [False] * count
    convergence_days = [0] * count
    current_convergence_days = [0] * count
    safety_pass = [False] * count
    safety_rank: list[float | None] = [None] * count

    for index in range(1, count):
        previous = frame.iloc[index - 1]
        current = frame.iloc[index]
        for column, target in (
            ("ma20", ma20_cross),
            ("ma60", ma60_cross),
            ("ma250", ma250_cross),
        ):
            values = [previous["close"], previous[column], current["close"], current[column]]
            target[index] = bool(
                not any(pd.isna(value) for value in values)
                and previous["close"] < previous[column]
                and current["close"] >= current[column]
            )
        death_values = [previous["ma60"], previous["ma250"], current["ma60"], current["ma250"]]
        death_cross[index] = bool(
            not any(pd.isna(value) for value in death_values)
            and previous["ma60"] >= previous["ma250"]
            and current["ma60"] < current["ma250"]
        )

    separations = pd.Series(index=frame.index, dtype=float)
    eligible = frame["ma60"].notna() & frame["ma250"].notna() & (frame["ma250"] != 0) & (frame["ma60"] < frame["ma250"])
    separations.loc[eligible] = (
        (frame.loc[eligible, "ma250"] - frame.loc[eligible, "ma60"])
        / frame.loc[eligible, "ma250"]
    )
    ordered = (
        frame["close"].notna()
        & frame["ma20"].notna()
        & frame["ma60"].notna()
        & (frame["close"] < frame["ma20"])
        & (frame["ma20"] < frame["ma60"])
    )
    for index in range(count):
        convergence_days[index] = int(
            ordered.iloc[max(0, index - CONVERGENCE_LOOKBACK_DAYS) : index].sum()
        )
        current_convergence_days[index] = int(
            ordered.iloc[
                max(0, index - CONVERGENCE_LOOKBACK_DAYS + 1) : index + 1
            ].sum()
        )
        current = separations.iloc[index]
        history = separations.iloc[max(0, index - SEPARATION_LOOKBACK_DAYS) : index].dropna()
        if pd.isna(current) or len(history) < SEPARATION_MIN_OBSERVATIONS:
            continue
        rank = float((history <= current).mean())
        safety_rank[index] = rank
        safety_pass[index] = bool(
            current >= separation_min_distance and rank >= separation_rank_threshold
        )

    death_indexes = [index for index, value in enumerate(death_cross) if value]
    warm_indexes = [index for index, value in enumerate(ma20_cross) if value]
    initial_start = [False] * count
    for index, crossed in enumerate(ma60_cross):
        if not crossed:
            continue
        has_death = any(max(1, index - SEPARATION_LOOKBACK_DAYS) <= value < index for value in death_indexes)
        has_warm = any(max(1, index - WARM_UP_LOOKBACK_DAYS) <= value < index for value in warm_indexes)
        initial_start[index] = bool(
            has_death
            and has_warm
            and convergence_days[index] >= CONVERGENCE_REQUIRED_DAYS
            and safety_pass[index]
        )

    latest_initial: int | None = None
    latest_trend: int | None = None
    records: list[dict[str, Any]] = []
    for index, row in frame.iterrows():
        if initial_start[index]:
            latest_initial = index
            latest_trend = None
        if latest_initial is not None and ma250_cross[index] and index >= latest_initial:
            latest_trend = index
        above_ma20 = pd.notna(row["ma20"]) and row["close"] >= row["ma20"]
        above_ma60 = pd.notna(row["ma60"]) and row["close"] >= row["ma60"]
        above_ma250 = pd.notna(row["ma250"]) and row["close"] >= row["ma250"]
        trend_active = bool(latest_trend is not None and above_ma250)
        initial_active = bool(latest_initial is not None and not trend_active and above_ma60)
        recent_warm = any(max(1, index - WARM_UP_LOOKBACK_DAYS) <= value < index + 1 for value in warm_indexes)
        warm_active = bool(recent_warm and safety_pass[index] and above_ma20)
        # 与生产引擎对齐：state_code 只描述收盘价落在哪条均线之上（纯几何），
        # 不带事件门控、不带安全边际门槛——否则回测与生产会各说一套。
        # 事件语义仍在 initial_start_active / trend_confirmed_active / invalidated 上。
        if above_ma250:
            state_code = "above_ma250"
        elif above_ma60:
            state_code = "above_ma60"
        elif above_ma20:
            state_code = "above_ma20"
        elif current_convergence_days[index] >= CONVERGENCE_REQUIRED_DAYS:
            state_code = "below_ma20_converged"
        else:
            state_code = "below_ma20"
        records.append(
            {
                "trade_date": str(row["trade_date"]),
                "state_code": state_code,
                "lifecycle_label": state_code,
                "initial_start_today": initial_start[index],
                "trend_confirmed_today": bool(latest_trend == index),
                "initial_start_active": initial_active,
                "trend_confirmed_active": trend_active,
                "initial_start_invalidated": bool(
                    latest_initial is not None and not initial_active and not trend_active
                ),
                "safety_margin_passed": safety_pass[index],
                "separation_rank": safety_rank[index],
                "convergence_days": current_convergence_days[index],
                "raw_ma60_cross": ma60_cross[index],
                "raw_ma250_cross": ma250_cross[index],
            }
        )
    return pd.DataFrame(records)


def resolve_targets(overview: dict[str, Any]) -> list[TargetSpec]:
    specs: list[TargetSpec] = []
    for target in overview.get("targets", []):
        code = str(target["code"])
        if code == "513970.SH":
            specs.append(
                TargetSpec(
                    code=code,
                    name=str(target["name"]),
                    kind="etf",
                    engine="hk_proxy_partial",
                    price_code=code,
                    execution_code=code,
                    benchmark_code=HK_BENCHMARK,
                )
            )
        elif code == "513230.SH":
            specs.append(
                TargetSpec(
                    code=code,
                    name=str(target["name"]),
                    kind="etf",
                    engine="hk_connect",
                    price_code="931454.CSI",
                    execution_code=code,
                    benchmark_code=HK_BENCHMARK,
                )
            )
        else:
            kind = str(target["kind"])
            specs.append(
                TargetSpec(
                    code=code,
                    name=str(target["name"]),
                    kind=kind,
                    engine="core",
                    price_code=str(target["indexCode"]),
                    execution_code=code if kind == "etf" else None,
                    benchmark_code=CORE_BENCHMARK,
                )
            )
    return specs


def select_weight_snapshot(snapshot: pd.DataFrame, *, hk_top_ten_only: bool = False) -> dict[str, Any]:
    ordered = snapshot.sort_values("weight", ascending=False).reset_index(drop=True)
    top_ten = ordered.head(LEADER_WATCH_COUNT)[["con_code", "weight"]].copy()
    if hk_top_ten_only:
        core = top_ten.copy()
    else:
        cumulative = ordered["weight"].cumsum()
        reached = cumulative[cumulative >= CORE_WEIGHT_COVERAGE]
        coverage_count = int(reached.index[0]) + 1 if not reached.empty else len(ordered)
        core_count = min(max(3, coverage_count), MAX_CORE_COUNT, len(ordered))
        core = ordered.head(core_count)[["con_code", "weight"]].copy()
    return {
        "date": str(ordered.iloc[0]["trade_date"]),
        "core": core.to_dict("records"),
        "topTen": top_ten.to_dict("records"),
    }


def build_snapshot_map(weights: pd.DataFrame, *, hk_top_ten_only: bool = False) -> list[dict[str, Any]]:
    if weights.empty:
        return []
    return [
        select_weight_snapshot(group, hk_top_ten_only=hk_top_ten_only)
        for _, group in weights.groupby("trade_date", sort=True)
    ]


def latest_snapshot(
    snapshots: list[dict[str, Any]],
    trade_date: str,
    cursor: int,
) -> tuple[dict[str, Any] | None, int]:
    while cursor + 1 < len(snapshots) and snapshots[cursor + 1]["date"] <= trade_date:
        cursor += 1
    if cursor >= 0 and snapshots[cursor]["date"] <= trade_date:
        return snapshots[cursor], cursor
    return None, cursor


def prepare_component_frame(frame: pd.DataFrame) -> pd.DataFrame:
    prepared = add_indicators(frame)
    return prepared.set_index("trade_date", drop=False)


def _row_on(frame: pd.DataFrame, trade_date: str) -> pd.Series | None:
    if trade_date not in frame.index:
        return None
    row = frame.loc[trade_date]
    return row.iloc[-1] if isinstance(row, pd.DataFrame) else row


def _has_history(frame: pd.DataFrame, trade_date: str) -> bool:
    return bool(len(frame) and str(frame.iloc[0]["trade_date"]) <= trade_date)


def evaluate_a_share_components(
    snapshot: dict[str, Any],
    trade_date: str,
    market_dates: list[str],
    components: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    usable_core: list[tuple[str, pd.Series | None]] = []
    selected_count = len(snapshot["core"])
    fresh_count = 0
    active_count = 0
    above_ma60_count = 0
    above_ma250_count = 0
    for item in snapshot["core"]:
        code = str(item["con_code"])
        frame = components.get(code)
        if frame is None or not _has_history(frame, trade_date):
            continue
        row = _row_on(frame, trade_date)
        usable_core.append((code, row))
        if row is None:
            continue
        fresh_count += 1
        active_count += int(
            (pd.notna(row.get("pct_chg")) and float(row["pct_chg"]) >= 5.0)
            or (pd.notna(row.get("ret5d")) and float(row["ret5d"]) >= 5.0)
        )
        above_ma60_count += int(
            pd.notna(row.get("ma60")) and float(row["close"]) >= float(row["ma60"])
        )
        above_ma250_count += int(
            pd.notna(row.get("ma250")) and float(row["close"]) >= float(row["ma250"])
        )

    strict_confirmed = False
    strict_seen = False
    secondary_alert = False
    date_position = len(market_dates) - 1
    for rank, item in enumerate(snapshot["topTen"], start=1):
        code = str(item["con_code"])
        frame = components.get(code)
        if frame is None or not _has_history(frame, trade_date):
            continue
        event_window = 5 if rank <= STRICT_LEADER_COUNT else 3
        window_dates = market_dates[max(0, date_position - event_window + 1) : date_position + 1]
        hits: list[int] = []
        for position, date in enumerate(window_dates):
            row = _row_on(frame, date)
            if row is not None and pd.notna(row.get("pct_chg")) and float(row["pct_chg"]) >= limit_threshold(code):
                hits.append(position)
        if not hits:
            continue
        hit_position = hits[-1]
        hit_date = window_dates[hit_position]
        hit_row = _row_on(frame, hit_date)
        current_row = _row_on(frame, trade_date)
        data_fresh = current_row is not None
        next_date = window_dates[hit_position + 1] if hit_position + 1 < len(window_dates) else None
        next_row = _row_on(frame, next_date) if next_date else None
        continuation_ok = bool(
            next_row is not None
            and pd.notna(next_row.get("pct_chg"))
            and float(next_row["pct_chg"]) > 0
        )
        latest_retained = bool(
            data_fresh
            and hit_row is not None
            and float(current_row["close"]) >= float(hit_row["close"])
        )
        qualified = bool(
            data_fresh
            and continuation_ok
            and (latest_retained if rank <= STRICT_LEADER_COUNT else True)
        )
        if rank <= STRICT_LEADER_COUNT:
            strict_seen = strict_seen or data_fresh
            strict_confirmed = strict_confirmed or qualified
        else:
            secondary_alert = secondary_alert or qualified

    core_count = len(usable_core)
    group_monitor = bool(
        core_count > 0
        and active_count >= 1
        and above_ma60_count / core_count >= 0.50
    )
    return {
        "core_count": core_count,
        "selected_count": selected_count,
        "fresh_count": fresh_count,
        "entry_data_fresh": bool(core_count == selected_count and fresh_count == selected_count),
        "active_count": active_count,
        "above_ma60_count": above_ma60_count,
        "above_ma250_count": above_ma250_count,
        "above_ma60_ratio": above_ma60_count / core_count if core_count else 0.0,
        "above_ma250_ratio": above_ma250_count / core_count if core_count else 0.0,
        "leader_pass": strict_confirmed,
        "leader_group_monitor": group_monitor,
        "leader_warning": bool((strict_seen or secondary_alert or group_monitor) and not strict_confirmed),
    }


def evaluate_hk_components(
    snapshot: dict[str, Any],
    trade_date: str,
    market_dates: list[str],
    components: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    fresh_count = 0
    above_ma60_count = 0
    positive_5d_count = 0
    strict_confirmed = False
    secondary_alert = False
    date_position = len(market_dates) - 1
    for rank, item in enumerate(snapshot["topTen"], start=1):
        code = str(item["con_code"])
        frame = components.get(code)
        if frame is None or not _has_history(frame, trade_date):
            continue
        current_row = _row_on(frame, trade_date)
        data_fresh = current_row is not None
        if data_fresh:
            fresh_count += 1
            above_ma60_count += int(
                pd.notna(current_row.get("ma60"))
                and float(current_row["close"]) > float(current_row["ma60"])
            )
            positive_5d_count += int(
                pd.notna(current_row.get("ret5d")) and float(current_row["ret5d"]) > 0
            )
        event_window = 5 if rank <= 3 else 3
        window_dates = market_dates[max(0, date_position - event_window + 1) : date_position + 1]
        hits: list[str] = []
        for date in window_dates:
            row = _row_on(frame, date)
            if row is None or pd.isna(row.get("pct_chg")):
                continue
            dynamic = max(
                LEADER_ABSOLUTE_RETURN,
                float(row["return_p95"]) if pd.notna(row.get("return_p95")) else LEADER_ABSOLUTE_RETURN,
            )
            if float(row["pct_chg"]) >= dynamic:
                hits.append(date)
        if not hits:
            continue
        hit_date = hits[-1]
        hit_row = _row_on(frame, hit_date)
        positions = frame.index.get_indexer([hit_date])
        if positions[0] < 0:
            continue
        eligible = frame[frame["trade_date"] <= trade_date]
        eligible_position = eligible.index.get_loc(hit_date)
        if isinstance(eligible_position, slice):
            eligible_position = eligible_position.stop - 1
        continuation = (
            eligible.iloc[int(eligible_position) + 1]
            if int(eligible_position) + 1 < len(eligible)
            else None
        )
        continuation_ok = bool(
            continuation is not None
            and pd.notna(continuation.get("pct_chg"))
            and float(continuation["pct_chg"]) > 0
        )
        latest_retained = bool(
            data_fresh and hit_row is not None and float(current_row["close"]) >= float(hit_row["close"])
        )
        qualified = bool(data_fresh and continuation_ok and latest_retained)
        if rank <= 3:
            strict_confirmed = strict_confirmed or qualified
        else:
            secondary_alert = secondary_alert or qualified
    breadth = bool(
        fresh_count == 10 and above_ma60_count >= 5 and positive_5d_count >= 5
    )
    leader_pass = strict_confirmed and breadth
    return {
        "core_count": 10,
        "selected_count": 10,
        "fresh_count": fresh_count,
        "entry_data_fresh": fresh_count == 10,
        "active_count": positive_5d_count,
        "above_ma60_count": above_ma60_count,
        "above_ma250_count": 0,
        "above_ma60_ratio": above_ma60_count / 10,
        "above_ma250_ratio": 0.0,
        "leader_pass": leader_pass,
        "leader_group_monitor": breadth,
        "leader_warning": bool(not leader_pass and (strict_confirmed or secondary_alert or breadth)),
    }


def add_core_price_features(price: pd.DataFrame, benchmark: pd.DataFrame, market_amount: pd.DataFrame) -> pd.DataFrame:
    frame = add_indicators(price)
    frame = frame.merge(market_amount, on="trade_date", how="left")
    frame["absorption_rate"] = frame["amount"] / frame["market_amount"]
    frame["absorption_rank_pct"] = rolling_current_rank(frame["absorption_rate"])
    valid = frame["ma250"].notna()
    frame["below_ma250"] = (frame["close"] < frame["ma250"]) & valid
    frame["below_ma250_5"] = (frame["close"] <= frame["ma250"] * 0.95) & valid
    frame["below_ma250_10"] = (frame["close"] <= frame["ma250"] * 0.90) & valid
    frame["valid_ma250"] = valid.astype(int)
    for column in ("below_ma250", "below_ma250_5", "below_ma250_10", "valid_ma250"):
        frame[f"{column}_120"] = frame[column].astype(int).rolling(120).sum()
    frame["close_to_high_120"] = frame["close"] / frame["close"].rolling(120).max()
    aligned = frame[["trade_date", "close"]].merge(
        benchmark[["trade_date", "close"]].rename(columns={"close": "benchmark_close"}),
        on="trade_date",
        how="left",
    )
    aligned["relative_excess_120"] = (
        aligned["close"].pct_change(120) - aligned["benchmark_close"].pct_change(120)
    )
    frame = frame.merge(
        aligned[["trade_date", "benchmark_close", "relative_excess_120"]],
        on="trade_date",
        how="left",
    )
    frame["price_confirm"] = (
        frame["ma250"].notna()
        & frame["ma250"].shift(1).notna()
        & (frame["close"] >= frame["ma250"])
        & (frame["close"].shift(1) >= frame["ma250"].shift(1))
    )
    frame["funding_min3"] = frame["absorption_rank_pct"].rolling(3).min()
    frame["funding_confirm"] = frame["funding_min3"] >= FUNDING_CONFIRM_PERCENTILE
    frame["ma60_gap"] = frame["close"] / frame["ma60"] - 1
    return frame.merge(build_lifecycle_series(frame), on="trade_date", how="left")


def add_hk_price_features(price: pd.DataFrame) -> pd.DataFrame:
    frame = add_indicators(price)
    frame["absorption_rank_pct"] = rolling_current_rank(frame["amount"], minimum=60)
    valid = frame["ma250"].notna()
    frame["below_ma250"] = (frame["close"] < frame["ma250"]) & valid
    frame["below_ma250_10"] = (frame["close"] <= frame["ma250"] * 0.90) & valid
    frame["valid_ma250"] = valid.astype(int)
    for column in ("below_ma250", "below_ma250_10", "valid_ma250"):
        frame[f"{column}_120"] = frame[column].astype(int).rolling(120).sum()
    frame["price_confirm"] = (
        frame["ma250"].notna()
        & frame["ma250"].shift(1).notna()
        & (frame["close"] > frame["ma250"])
        & (frame["close"].shift(1) > frame["ma250"].shift(1))
    )
    frame["funding_min3"] = frame["absorption_rank_pct"].rolling(3).min()
    frame["funding_confirm"] = frame["funding_min3"] >= FUNDING_CONFIRM_PERCENTILE
    frame["ma60_gap"] = frame["close"] / frame["ma60"] - 1
    return frame.merge(build_lifecycle_series(frame), on="trade_date", how="left")


def empty_component_state() -> dict[str, Any]:
    return {
        "core_count": 0,
        "selected_count": 0,
        "fresh_count": 0,
        "entry_data_fresh": False,
        "active_count": 0,
        "above_ma60_count": 0,
        "above_ma250_count": 0,
        "above_ma60_ratio": 0.0,
        "above_ma250_ratio": 0.0,
        "leader_pass": False,
        "leader_group_monitor": False,
        "leader_warning": False,
    }


def _weight_age(as_of: str, weight_date: str | None) -> int | None:
    if not weight_date:
        return None
    return (
        datetime.strptime(as_of, "%Y%m%d")
        - datetime.strptime(weight_date, "%Y%m%d")
    ).days


def _int_or_zero(value: Any) -> int:
    return 0 if value is None or pd.isna(value) else int(value)


def build_core_target_history(
    spec: TargetSpec,
    price: pd.DataFrame,
    benchmark: pd.DataFrame,
    market_amount: pd.DataFrame,
    snapshots: list[dict[str, Any]],
    components: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    frame = add_core_price_features(price, benchmark, market_amount)
    records: list[dict[str, Any]] = []
    market_dates: list[str] = []
    snapshot_cursor = -1
    for index, row in frame.iterrows():
        trade_date = str(row["trade_date"])
        market_dates.append(trade_date)
        snapshot, snapshot_cursor = latest_snapshot(snapshots, trade_date, snapshot_cursor)
        component_state = (
            evaluate_a_share_components(snapshot, trade_date, market_dates, components)
            if snapshot is not None
            else empty_component_state()
        )
        complete_structure = bool(row.get("valid_ma250_120") == 120)
        below_days = _int_or_zero(row.get("below_ma250_120"))
        below_5_days = _int_or_zero(row.get("below_ma250_5_120"))
        below_10_days = _int_or_zero(row.get("below_ma250_10_120"))
        deep_pass = (
            below_days >= LOW_DEEP_10_PASS_MIN_BELOW_DAYS
            and below_10_days >= LOW_DEEP_10_PASS_DAYS
        )
        deep_warning = (
            below_days >= LOW_DEEP_10_WARNING_MIN_BELOW_DAYS
            and below_10_days >= LOW_DEEP_10_WARNING_DAYS
        )
        structure_pass = bool(
            complete_structure
            and (below_5_days >= LOW_BELOW_MA250_5_PASS_DAYS or deep_pass)
        )
        structure_warning = bool(
            complete_structure
            and not structure_pass
            and (below_5_days >= LOW_BELOW_MA250_5_WARNING_DAYS or deep_warning)
        )
        price_confirm = bool(row.get("price_confirm"))
        funding_confirm = bool(row.get("funding_confirm"))
        breakout_pass = price_confirm and funding_confirm
        breakout_emerged = price_confirm or funding_confirm
        ma60_near = bool(pd.notna(row.get("ma60_gap")) and float(row["ma60_gap"]) >= -0.03)
        condition_a = bool(
            pd.notna(row.get("ma250")) and float(row["close"]) > float(row["ma250"]) * 1.15
        )
        condition_b = bool(
            pd.notna(row.get("relative_excess_120")) and float(row["relative_excess_120"]) >= 0.15
        )
        condition_c = bool(
            pd.notna(row.get("close_to_high_120"))
            and float(row["close_to_high_120"]) >= 0.95
            and component_state["above_ma60_ratio"] >= 0.67
            and component_state["above_ma250_ratio"] >= 0.67
        )
        trend_extension = condition_a or condition_b or condition_c
        if trend_extension:
            label = "趋势延续"
        elif structure_pass and breakout_pass and component_state["leader_pass"]:
            label = "启动确认"
        elif structure_pass and breakout_emerged and component_state["leader_group_monitor"]:
            label = "接近启动"
        elif (structure_pass or structure_warning) and ma60_near:
            label = "观察中"
        else:
            label = "未启动"
        weight_date = snapshot["date"] if snapshot else None
        weight_age = _weight_age(trade_date, weight_date)
        history_ready = index + 1 >= 750
        weight_fresh = bool(weight_age is not None and 0 <= weight_age <= 60)
        entry_guard = bool(
            history_ready and weight_fresh and component_state["entry_data_fresh"]
        )
        all_stages = structure_pass and breakout_pass and component_state["leader_pass"]
        records.append(
            {
                "code": spec.code,
                "name": spec.name,
                "engine": spec.engine,
                "trade_date": trade_date,
                "primary_label": label,
                "structure_complete": complete_structure,
                "structure_pass": structure_pass,
                "structure_warning": structure_warning,
                "below_ma250_days": below_days,
                "below_ma250_5_days": below_5_days,
                "below_ma250_10_days": below_10_days,
                "price_confirm": price_confirm,
                "funding_confirm": funding_confirm,
                "funding_min3": row.get("funding_min3"),
                "breakout_pass": breakout_pass,
                "breakout_emerged": breakout_emerged,
                "ma60_near": ma60_near,
                "ma60_gap": row.get("ma60_gap"),
                "leader_pass": component_state["leader_pass"],
                "leader_warning": component_state["leader_warning"],
                "leader_group_monitor": component_state["leader_group_monitor"],
                "above_ma60_ratio": component_state["above_ma60_ratio"],
                "above_ma250_ratio": component_state["above_ma250_ratio"],
                "trend_extension": trend_extension,
                "relative_excess_120": row.get("relative_excess_120"),
                "close_to_high_120": row.get("close_to_high_120"),
                "close": row.get("close"),
                "ma60": row.get("ma60"),
                "ma250": row.get("ma250"),
                "weight_date": weight_date,
                "weight_age_days": weight_age,
                "history_ready": history_ready,
                "entry_data_fresh": component_state["entry_data_fresh"],
                "entry_guard_passed": entry_guard,
                "lifecycle_label": row.get("lifecycle_label"),
                "initial_start_today": bool(row.get("initial_start_today")),
                "trend_confirmed_today": bool(row.get("trend_confirmed_today")),
                "initial_start_active": bool(row.get("initial_start_active")),
                "trend_confirmed_active": bool(row.get("trend_confirmed_active")),
                "raw_ma60_cross": bool(row.get("raw_ma60_cross")),
                "raw_ma250_cross": bool(row.get("raw_ma250_cross")),
                "candidate_eligible": bool(label == "接近启动" and ma60_near and entry_guard),
                "starter_eligible": bool(row.get("initial_start_active") and entry_guard),
                "confirmed_eligible": bool(row.get("trend_confirmed_active") and all_stages and entry_guard),
            }
        )
    return pd.DataFrame(records)


def build_hk_target_history(
    spec: TargetSpec,
    price: pd.DataFrame,
    snapshots: list[dict[str, Any]],
    components: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    frame = add_hk_price_features(price)
    records: list[dict[str, Any]] = []
    market_dates: list[str] = []
    snapshot_cursor = -1
    partial = spec.engine == "hk_proxy_partial"
    for index, row in frame.iterrows():
        trade_date = str(row["trade_date"])
        market_dates.append(trade_date)
        snapshot, snapshot_cursor = latest_snapshot(snapshots, trade_date, snapshot_cursor)
        component_state = (
            evaluate_hk_components(snapshot, trade_date, market_dates, components)
            if snapshot is not None and not partial
            else empty_component_state()
        )
        complete_structure = bool(row.get("valid_ma250_120") == 120)
        below_days = _int_or_zero(row.get("below_ma250_120"))
        below_10_days = _int_or_zero(row.get("below_ma250_10_120"))
        structure_pass = bool(
            complete_structure and (below_days >= 60 or below_10_days >= 24)
        )
        structure_warning = bool(
            complete_structure
            and not structure_pass
            and (below_days >= 40 or below_10_days >= 12)
        )
        price_confirm = bool(row.get("price_confirm"))
        funding_confirm = bool(row.get("funding_confirm"))
        breakout_pass = price_confirm and funding_confirm
        ma60_above = bool(pd.notna(row.get("ma60")) and float(row["close"]) > float(row["ma60"]))
        breakout_warning = bool(
            not breakout_pass and (ma60_above or price_confirm or funding_confirm)
        )
        leader_pass = component_state["leader_pass"] if not partial else False
        leader_warning = component_state["leader_warning"] if not partial else False
        stage_pass_count = sum([structure_pass, breakout_pass, leader_pass])
        if partial:
            label = None
        elif stage_pass_count == 3:
            label = "启动确认"
        elif structure_pass and breakout_pass and leader_warning:
            label = "接近启动"
        elif stage_pass_count or structure_warning or breakout_warning or leader_warning:
            label = "观察中"
        else:
            label = "未启动"
        weight_date = snapshot["date"] if snapshot else None
        weight_age = _weight_age(trade_date, weight_date)
        history_ready = index + 1 >= 750
        weight_fresh = bool(weight_age is not None and 0 <= weight_age <= 60)
        entry_guard = bool(
            not partial
            and history_ready
            and weight_fresh
            and component_state["entry_data_fresh"]
        )
        all_stages = structure_pass and breakout_pass and leader_pass
        records.append(
            {
                "code": spec.code,
                "name": spec.name,
                "engine": spec.engine,
                "trade_date": trade_date,
                "primary_label": label,
                "structure_complete": complete_structure,
                "structure_pass": structure_pass,
                "structure_warning": structure_warning,
                "below_ma250_days": below_days,
                "below_ma250_5_days": None,
                "below_ma250_10_days": below_10_days,
                "price_confirm": price_confirm,
                "funding_confirm": funding_confirm,
                "funding_min3": row.get("funding_min3"),
                "breakout_pass": breakout_pass,
                "breakout_emerged": bool(price_confirm or funding_confirm),
                "ma60_near": ma60_above,
                "ma60_gap": row.get("ma60_gap"),
                "leader_pass": leader_pass,
                "leader_warning": leader_warning,
                "leader_group_monitor": component_state["leader_group_monitor"],
                "above_ma60_ratio": component_state["above_ma60_ratio"],
                "above_ma250_ratio": 0.0,
                "trend_extension": False,
                "relative_excess_120": None,
                "close_to_high_120": None,
                "close": row.get("close"),
                "ma60": row.get("ma60"),
                "ma250": row.get("ma250"),
                "weight_date": weight_date,
                "weight_age_days": weight_age,
                "history_ready": history_ready,
                "entry_data_fresh": component_state["entry_data_fresh"],
                "entry_guard_passed": entry_guard,
                "lifecycle_label": row.get("lifecycle_label"),
                "initial_start_today": bool(row.get("initial_start_today")),
                "trend_confirmed_today": bool(row.get("trend_confirmed_today")),
                "initial_start_active": bool(row.get("initial_start_active")),
                "trend_confirmed_active": bool(row.get("trend_confirmed_active")),
                "raw_ma60_cross": bool(row.get("raw_ma60_cross")),
                "raw_ma250_cross": bool(row.get("raw_ma250_cross")),
                "candidate_eligible": bool(label == "接近启动" and entry_guard),
                "starter_eligible": bool(row.get("initial_start_active") and entry_guard),
                "confirmed_eligible": bool(row.get("trend_confirmed_active") and all_stages and entry_guard),
            }
        )
    return pd.DataFrame(records)


def extract_events(history: pd.DataFrame) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    previous_label: str | None = None
    prior_flags = {
        "structure_pass": False,
        "breakout_pass": False,
        "leader_pass": False,
        "candidate_eligible": False,
        "starter_eligible": False,
        "confirmed_eligible": False,
    }
    transition_names = {
        "structure_pass": "stage_structure_pass",
        "breakout_pass": "stage_breakout_pass",
        "leader_pass": "stage_leader_pass",
        "candidate_eligible": "allocation_candidate",
        "starter_eligible": "allocation_starter",
        "confirmed_eligible": "allocation_confirmed",
    }
    direct_names = {
        "raw_ma60_cross": "raw_ma60_cross",
        "initial_start_today": "lifecycle_initial_start",
        "raw_ma250_cross": "raw_ma250_cross",
        "trend_confirmed_today": "lifecycle_trend_confirmation",
    }
    for position, row in history.reset_index(drop=True).iterrows():
        label = row.get("primary_label")
        if isinstance(label, str) and label in PRIMARY_LABELS and label != previous_label:
            events.append(
                {
                    "code": row["code"],
                    "name": row["name"],
                    "engine": row["engine"],
                    "eventType": f"label_{label}",
                    "signalDate": row["trade_date"],
                    "signalPosition": position,
                    "primaryLabel": label,
                }
            )
        previous_label = label if isinstance(label, str) else previous_label
        for field, event_name in transition_names.items():
            current = bool(row.get(field))
            if current and not prior_flags[field]:
                events.append(
                    {
                        "code": row["code"],
                        "name": row["name"],
                        "engine": row["engine"],
                        "eventType": event_name,
                        "signalDate": row["trade_date"],
                        "signalPosition": position,
                        "primaryLabel": label,
                    }
                )
            prior_flags[field] = current
        for field, event_name in direct_names.items():
            if bool(row.get(field)):
                events.append(
                    {
                        "code": row["code"],
                        "name": row["name"],
                        "engine": row["engine"],
                        "eventType": event_name,
                        "signalDate": row["trade_date"],
                        "signalPosition": position,
                        "primaryLabel": label,
                    }
                )
    return events


_OUTCOME_CONTEXT_CACHE: dict[int, tuple[pd.DataFrame, list[str], dict[str, int]]] = {}


def _outcome_context(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, list[str], dict[str, int]]:
    key = id(frame)
    cached = _OUTCOME_CONTEXT_CACHE.get(key)
    if cached is not None:
        return cached
    normalized = normalize_daily(frame)
    dates = normalized["trade_date"].astype(str).tolist()
    context = (normalized, dates, {trade_date: position for position, trade_date in enumerate(dates)})
    _OUTCOME_CONTEXT_CACHE[key] = context
    return context


def _value_on_or_before(
    frame: pd.DataFrame, dates: list[str], trade_date: str, column: str
) -> float | None:
    position = bisect_right(dates, trade_date) - 1
    if position < 0:
        return None
    value = frame.iloc[int(position)].get(column)
    return float(value) if pd.notna(value) else None


def add_forward_outcomes(
    event: dict[str, Any],
    signal_price: pd.DataFrame,
    benchmark: pd.DataFrame,
    execution_price: pd.DataFrame | None,
) -> dict[str, Any]:
    result = dict(event)
    signal_price, dates, signal_positions = _outcome_context(signal_price)
    benchmark, benchmark_dates, _ = _outcome_context(benchmark)
    execution_context = (
        _outcome_context(execution_price) if execution_price is not None else None
    )
    signal_position = signal_positions.get(event["signalDate"])
    if signal_position is None:
        return result
    signal_close = float(signal_price.iloc[signal_position]["close"])
    benchmark_start = _value_on_or_before(
        benchmark, benchmark_dates, event["signalDate"], "close"
    )
    for horizon in HORIZONS:
        end_position = signal_position + horizon
        prefix = f"d{horizon}"
        if end_position < len(signal_price):
            end_row = signal_price.iloc[end_position]
            end_date = str(end_row["trade_date"])
            target_return = float(end_row["close"] / signal_close - 1)
            path = signal_price.iloc[signal_position + 1 : end_position + 1]
            path_returns = path["close"] / signal_close - 1
            benchmark_end = _value_on_or_before(
                benchmark, benchmark_dates, end_date, "close"
            )
            benchmark_return = (
                benchmark_end / benchmark_start - 1
                if benchmark_start not in (None, 0) and benchmark_end is not None
                else None
            )
            result.update(
                {
                    f"{prefix}EndDate": end_date,
                    f"{prefix}ReturnPct": target_return * 100,
                    f"{prefix}BenchmarkReturnPct": (
                        benchmark_return * 100 if benchmark_return is not None else None
                    ),
                    f"{prefix}ExcessReturnPct": (
                        (target_return - benchmark_return) * 100
                        if benchmark_return is not None
                        else None
                    ),
                    f"{prefix}MaxAdversePct": float(path_returns.min() * 100),
                    f"{prefix}MaxFavorablePct": float(path_returns.max() * 100),
                }
            )
        if execution_context is not None:
            execution, execution_dates, _ = execution_context
            entry_position = bisect_right(execution_dates, event["signalDate"])
            exit_position = entry_position + horizon - 1
            if entry_position < len(execution) and exit_position < len(execution):
                entry_open = execution.iloc[entry_position].get("open")
                exit_close = execution.iloc[exit_position].get("close")
                if pd.notna(entry_open) and pd.notna(exit_close) and float(entry_open) != 0:
                    result[f"{prefix}NextOpenEntryDate"] = str(
                        execution.iloc[entry_position]["trade_date"]
                    )
                    result[f"{prefix}NextOpenReturnPct"] = (
                        float(exit_close) / float(entry_open) - 1
                    ) * 100
    return result


def _period_for_date(trade_date: str) -> list[str]:
    periods = ["full"]
    if trade_date <= "20231231":
        periods.append("backcast_2019_2023")
    else:
        periods.append("recent_2024_2026")
    return periods


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _median(values: list[float]) -> float | None:
    return float(pd.Series(values).median()) if values else None


def summarize_event_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    event_types = sorted({row["eventType"] for row in rows})
    periods = ("full", "backcast_2019_2023", "recent_2024_2026")
    for event_type in event_types:
        type_rows = [row for row in rows if row["eventType"] == event_type]
        for period in periods:
            period_rows = [
                row for row in type_rows if period in _period_for_date(row["signalDate"])
            ]
            for horizon in HORIZONS:
                prefix = f"d{horizon}"
                completed = [
                    row for row in period_rows if row.get(f"{prefix}ReturnPct") is not None
                ]
                returns = [float(row[f"{prefix}ReturnPct"]) for row in completed]
                excess = [
                    float(row[f"{prefix}ExcessReturnPct"])
                    for row in completed
                    if row.get(f"{prefix}ExcessReturnPct") is not None
                ]
                adverse = [float(row[f"{prefix}MaxAdversePct"]) for row in completed]
                favorable = [float(row[f"{prefix}MaxFavorablePct"]) for row in completed]
                executable = [
                    float(row[f"{prefix}NextOpenReturnPct"])
                    for row in completed
                    if row.get(f"{prefix}NextOpenReturnPct") is not None
                ]
                non_overlap: list[dict[str, Any]] = []
                last_position: dict[str, int] = {}
                for row in sorted(completed, key=lambda value: (value["code"], value["signalDate"])):
                    position = int(row["signalPosition"])
                    if position - last_position.get(row["code"], -10_000) > horizon:
                        non_overlap.append(row)
                        last_position[row["code"]] = position
                non_overlap_excess = [
                    float(row[f"{prefix}ExcessReturnPct"])
                    for row in non_overlap
                    if row.get(f"{prefix}ExcessReturnPct") is not None
                ]
                summaries.append(
                    {
                        "eventType": event_type,
                        "period": period,
                        "horizonTradeDays": horizon,
                        "eventCount": len(period_rows),
                        "completedCount": len(completed),
                        "meanReturnPct": _mean(returns),
                        "medianReturnPct": _median(returns),
                        "positiveRatePct": (
                            sum(value > 0 for value in returns) / len(returns) * 100
                            if returns
                            else None
                        ),
                        "meanExcessReturnPct": _mean(excess),
                        "medianExcessReturnPct": _median(excess),
                        "positiveExcessRatePct": (
                            sum(value > 0 for value in excess) / len(excess) * 100
                            if excess
                            else None
                        ),
                        "meanMaxAdversePct": _mean(adverse),
                        "meanMaxFavorablePct": _mean(favorable),
                        "executableCount": len(executable),
                        "meanNextOpenReturnPct": _mean(executable),
                        "nextOpenPositiveRatePct": (
                            sum(value > 0 for value in executable) / len(executable) * 100
                            if executable
                            else None
                        ),
                        "nonOverlapCount": len(non_overlap),
                        "nonOverlapMeanExcessPct": _mean(non_overlap_excess),
                        "nonOverlapPositiveExcessRatePct": (
                            sum(value > 0 for value in non_overlap_excess)
                            / len(non_overlap_excess)
                            * 100
                            if non_overlap_excess
                            else None
                        ),
                    }
                )
    return summaries


def build_baseline_rows(
    histories: dict[str, pd.DataFrame],
    signal_prices: dict[str, pd.DataFrame],
    benchmarks: dict[str, pd.DataFrame],
    specs: dict[str, TargetSpec],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for code, history in histories.items():
        complete_positions = history.index[history["structure_complete"]].tolist()
        if not complete_positions:
            continue
        first_complete_position = int(complete_positions[0])
        for horizon in HORIZONS:
            for position in range(first_complete_position, len(history), horizon + 1):
                row = history.iloc[position]
                event = {
                    "code": code,
                    "name": row["name"],
                    "engine": row["engine"],
                    "eventType": f"baseline_unconditional_every_{horizon}d",
                    "signalDate": row["trade_date"],
                    "signalPosition": position,
                    "primaryLabel": row.get("primary_label"),
                }
                rows.append(
                    add_forward_outcomes(
                        event,
                        signal_prices[code],
                        benchmarks[specs[code].benchmark_code],
                        None,
                    )
                )
    return rows


def _fmt(value: Any, digits: int = 2) -> str:
    return "-" if value is None or pd.isna(value) else f"{float(value):.{digits}f}"


def write_report(
    path: Path,
    meta: dict[str, Any],
    summaries: list[dict[str, Any]],
    target_summary: list[dict[str, Any]],
    sensitivity: list[dict[str, Any]],
) -> None:
    focus = [
        "raw_ma60_cross",
        "lifecycle_initial_start",
        "raw_ma250_cross",
        "lifecycle_trend_confirmation",
        "label_观察中",
        "label_接近启动",
        "label_启动确认",
        "allocation_candidate",
        "allocation_starter",
        "allocation_confirmed",
        "baseline_unconditional_every_20d",
    ]
    rows_20 = {
        row["eventType"]: row
        for row in summaries
        if row["period"] == "full"
        and row["horizonTradeDays"] == 20
        and row["eventType"] in focus
    }
    lines = [
        "# ETF Watch 行业启动策略全面回测",
        "",
        f"- 生成时间：{meta['generatedAt']}",
        f"- 数据区间：{meta['startDate']}—{meta['endDate']}",
        f"- 当前目标池：{meta['targetCount']} 个；完整主标签回放 {meta['fullPrimaryReplayTargetCount']} 个",
        "- 口径：信号日收盘后可知；另列下一交易日开盘进入的可执行收益；不模拟账户资金配置。",
        "",
        "## 20个交易日总体结果",
        "",
        "| 信号 | 样本 | 平均收益 | 平均超额 | 超额胜率 | 非重叠超额 | 次日开盘收益 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for event_type in focus:
        row = rows_20.get(event_type)
        if not row:
            continue
        lines.append(
            f"| {event_type} | {row['completedCount']} | {_fmt(row['meanReturnPct'])}% | "
            f"{_fmt(row['meanExcessReturnPct'])}% | {_fmt(row['positiveExcessRatePct'])}% | "
            f"{_fmt(row['nonOverlapMeanExcessPct'])}% | {_fmt(row['meanNextOpenReturnPct'])}% |"
        )
    lines.extend(
        [
            "",
            "## 历史回放与近期样本对照（20日）",
            "",
            "| 信号 | 分段 | 样本 | 平均超额 | 超额胜率 | 非重叠超额 |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    for event_type in (
        "lifecycle_initial_start",
        "lifecycle_trend_confirmation",
        "label_接近启动",
        "label_启动确认",
        "baseline_unconditional_every_20d",
    ):
        for period in ("backcast_2019_2023", "recent_2024_2026"):
            row = next(
                (
                    item
                    for item in summaries
                    if item["eventType"] == event_type
                    and item["period"] == period
                    and item["horizonTradeDays"] == 20
                ),
                None,
            )
            if row:
                lines.append(
                    f"| {event_type} | {period} | {row['completedCount']} | "
                    f"{_fmt(row['meanExcessReturnPct'])}% | {_fmt(row['positiveExcessRatePct'])}% | "
                    f"{_fmt(row['nonOverlapMeanExcessPct'])}% |"
                )
    lines.extend(
        [
            "",
            "## 单变量敏感性（20日）",
            "",
            "| 参数 | 数值 | 观察事件 | 样本 | 平均超额 | 超额胜率 | 非重叠超额 |",
            "|---|---:|---|---:|---:|---:|---:|",
        ]
    )
    for row in sensitivity:
        if (
            row["eventType"] == "label_启动确认"
            or row["eventType"] == "lifecycle_initial_start"
        ):
            lines.append(
                f"| {row['parameter']} | {row['value']} | {row['eventType']} | "
                f"{row['completedCount']} | {_fmt(row['meanExcessReturnPct'])}% | "
                f"{_fmt(row['positiveExcessRatePct'])}% | {_fmt(row['nonOverlapMeanExcessPct'])}% |"
            )
    lines.extend(
        [
            "",
            "## 标的覆盖与信号数量",
            "",
            "| 标的 | 引擎 | 首个有效日 | 标签事件 | 初始启动 | 年线确认 | 启动确认 |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in target_summary:
        lines.append(
            f"| {row['code']} {row['name']} | {row['engine']} | {row['firstCompleteDate'] or '-'} | "
            f"{row['labelEventCount']} | {row['initialStartCount']} | {row['trendConfirmationCount']} | "
            f"{row['startupConfirmationCount']} |"
        )
    lines.extend(
        [
            "",
            "## 解释限制",
            "",
            "- 这不是严格意义上的全新样本外检验：规则已经在2026-08-13前形成。2019—2023称为历史回放，2024以后称为近期样本；真正前瞻样本从策略冻结后开始积累。",
            "- 目标池使用当前25个标的，仍存在目标选择存活偏差；成分股层已使用逐月历史权重，未用当前成分回填过去。",
            "- 513970只提供当前恒生消费前十大，无法无前视地重建历史第三层，因此仅回测价格、资金和均线生命周期，不纳入完整主标签统计。",
            "- 龙头确认是行业状态信号，不是追涨龙头股指令；可执行收益按ETF下一交易日开盘计算。",
            "- 回测未计佣金、冲击成本和ETF折溢价；这些仍属于外部执行层。",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def relabel_core_history(
    history: pd.DataFrame,
    *,
    parameter: str,
    value: float,
) -> pd.DataFrame:
    result = history.copy().reset_index(drop=True)
    path_a_days = int(value) if parameter == "structure_path_a_days" else 60
    funding_threshold = value if parameter == "funding_percentile" else 0.80
    ma60_gap_threshold = value if parameter == "ma60_observation_gap" else -0.03
    trend_gap = value if parameter == "trend_extension_gap" else 0.15
    relative_threshold = value if parameter == "relative_excess_threshold" else 0.15
    high_threshold = value if parameter == "close_to_high_threshold" else 0.95
    if parameter == "structure_path_a_ratio":
        valid = result["ma250"].notna()
        path_a_counts = (
            ((result["close"] <= result["ma250"] * value) & valid)
            .astype(int)
            .rolling(120)
            .sum()
        )
    else:
        path_a_counts = result["below_ma250_5_days"]
    labels: list[str] = []
    structure_values: list[bool] = []
    breakout_values: list[bool] = []
    for index, row in result.iterrows():
        complete = bool(row["structure_complete"])
        deep_pass = (
            int(row["below_ma250_days"]) >= LOW_DEEP_10_PASS_MIN_BELOW_DAYS
            and int(row["below_ma250_10_days"]) >= LOW_DEEP_10_PASS_DAYS
        )
        deep_warning = (
            int(row["below_ma250_days"]) >= LOW_DEEP_10_WARNING_MIN_BELOW_DAYS
            and int(row["below_ma250_10_days"]) >= LOW_DEEP_10_WARNING_DAYS
        )
        path_count = _int_or_zero(path_a_counts.iloc[index])
        structure_pass = bool(complete and (path_count >= path_a_days or deep_pass))
        structure_warning = bool(
            complete
            and not structure_pass
            and (path_count >= LOW_BELOW_MA250_5_WARNING_DAYS or deep_warning)
        )
        funding = bool(
            pd.notna(row.get("funding_min3")) and float(row["funding_min3"]) >= funding_threshold
        )
        breakout_pass = bool(row["price_confirm"] and funding)
        breakout_emerged = bool(row["price_confirm"] or funding)
        ma60_near = bool(pd.notna(row.get("ma60_gap")) and float(row["ma60_gap"]) >= ma60_gap_threshold)
        condition_a = bool(
            pd.notna(row.get("ma250"))
            and float(row["close"]) > float(row["ma250"]) * (1 + trend_gap)
        )
        condition_b = bool(
            pd.notna(row.get("relative_excess_120"))
            and float(row["relative_excess_120"]) >= relative_threshold
        )
        condition_c = bool(
            pd.notna(row.get("close_to_high_120"))
            and float(row["close_to_high_120"]) >= high_threshold
            and float(row["above_ma60_ratio"]) >= 0.67
            and float(row["above_ma250_ratio"]) >= 0.67
        )
        if condition_a or condition_b or condition_c:
            label = "趋势延续"
        elif structure_pass and breakout_pass and bool(row["leader_pass"]):
            label = "启动确认"
        elif structure_pass and breakout_emerged and bool(row["leader_group_monitor"]):
            label = "接近启动"
        elif (structure_pass or structure_warning) and ma60_near:
            label = "观察中"
        else:
            label = "未启动"
        labels.append(label)
        structure_values.append(structure_pass)
        breakout_values.append(breakout_pass)
    result["primary_label"] = labels
    result["structure_pass"] = structure_values
    result["breakout_pass"] = breakout_values
    return result


def run_sensitivity(
    histories: dict[str, pd.DataFrame],
    signal_prices: dict[str, pd.DataFrame],
    benchmarks: dict[str, pd.DataFrame],
    specs: dict[str, TargetSpec],
) -> list[dict[str, Any]]:
    grid: dict[str, list[float]] = {
        "structure_path_a_days": [50, 60, 70],
        "structure_path_a_ratio": [0.94, 0.95, 0.96],
        "funding_percentile": [0.75, 0.80, 0.85],
        "ma60_observation_gap": [-0.02, -0.03, -0.04],
        "trend_extension_gap": [0.10, 0.15, 0.20],
        "relative_excess_threshold": [0.10, 0.15, 0.20],
        "close_to_high_threshold": [0.93, 0.95, 0.97],
    }
    outputs: list[dict[str, Any]] = []
    core_codes = [code for code, spec in specs.items() if spec.engine == "core"]
    for parameter, values in grid.items():
        for value in values:
            event_rows: list[dict[str, Any]] = []
            for code in core_codes:
                relabeled = relabel_core_history(
                    histories[code], parameter=parameter, value=value
                )
                for event in extract_events(relabeled):
                    if event["eventType"] not in {
                        "label_观察中",
                        "label_接近启动",
                        "label_启动确认",
                        "label_趋势延续",
                    }:
                        continue
                    event_rows.append(
                        add_forward_outcomes(
                            event,
                            signal_prices[code],
                            benchmarks[CORE_BENCHMARK],
                            None,
                        )
                    )
            summaries = summarize_event_rows(event_rows)
            for event_type in (
                "label_观察中",
                "label_接近启动",
                "label_启动确认",
                "label_趋势延续",
            ):
                summary = next(
                    (
                        row
                        for row in summaries
                        if row["eventType"] == event_type
                        and row["period"] == "full"
                        and row["horizonTradeDays"] == 20
                    ),
                    None,
                )
                outputs.append(
                    {
                        "parameter": parameter,
                        "value": value,
                        "eventType": event_type,
                        "eventCount": summary["eventCount"] if summary else 0,
                        "completedCount": summary["completedCount"] if summary else 0,
                        "meanExcessReturnPct": summary["meanExcessReturnPct"] if summary else None,
                        "positiveExcessRatePct": summary["positiveExcessRatePct"] if summary else None,
                        "nonOverlapMeanExcessPct": summary["nonOverlapMeanExcessPct"] if summary else None,
                    }
                )

    lifecycle_grid = {
        "lifecycle_min_separation": [0.04, 0.05, 0.06],
        "lifecycle_rank_threshold": [0.60, 0.70, 0.80],
    }
    for parameter, values in lifecycle_grid.items():
        for value in values:
            event_rows = []
            for code, spec in specs.items():
                price = add_indicators(signal_prices[code])
                lifecycle = build_lifecycle_series(
                    price,
                    separation_min_distance=(
                        value if parameter == "lifecycle_min_separation" else 0.05
                    ),
                    separation_rank_threshold=(
                        value if parameter == "lifecycle_rank_threshold" else 0.70
                    ),
                )
                for position, row in lifecycle.iterrows():
                    if not bool(row["initial_start_today"]):
                        continue
                    event = {
                        "code": code,
                        "name": spec.name,
                        "engine": spec.engine,
                        "eventType": "lifecycle_initial_start",
                        "signalDate": row["trade_date"],
                        "signalPosition": position,
                        "primaryLabel": None,
                    }
                    event_rows.append(
                        add_forward_outcomes(
                            event,
                            signal_prices[code],
                            benchmarks[spec.benchmark_code],
                            None,
                        )
                    )
            summary = next(
                (
                    row
                    for row in summarize_event_rows(event_rows)
                    if row["eventType"] == "lifecycle_initial_start"
                    and row["period"] == "full"
                    and row["horizonTradeDays"] == 20
                ),
                None,
            )
            outputs.append(
                {
                    "parameter": parameter,
                    "value": value,
                    "eventType": "lifecycle_initial_start",
                    "eventCount": summary["eventCount"] if summary else 0,
                    "completedCount": summary["completedCount"] if summary else 0,
                    "meanExcessReturnPct": summary["meanExcessReturnPct"] if summary else None,
                    "positiveExcessRatePct": summary["positiveExcessRatePct"] if summary else None,
                    "nonOverlapMeanExcessPct": summary["nonOverlapMeanExcessPct"] if summary else None,
                }
            )
    return outputs


def _json_default(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    if pd.isna(value):
        return None
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def validate_lifecycle_replay(price: pd.DataFrame, replay: pd.DataFrame, code: str) -> None:
    prepared = add_indicators(price)
    expected = evaluate_moving_average_lifecycle(prepared)
    latest = replay.iloc[-1]
    replay_state = latest.get("state_code")
    if replay_state is None or (isinstance(replay_state, float) and pd.isna(replay_state)):
        replay_state = latest.get("lifecycle_label")
    comparisons = {
        "stateCode": (str(replay_state), expected["stateCode"]),
        "ma60CrossUpToday": (bool(latest["initial_start_today"]), expected["ma60CrossUpToday"]),
        "aboveMa250Today": (bool(latest["trend_confirmed_today"]), expected["aboveMa250Today"]),
        "stateAboveMa60": (bool(latest["initial_start_active"]), expected["stateAboveMa60"]),
        "stateAboveMa250": (bool(latest["trend_confirmed_active"]), expected["stateAboveMa250"]),
    }
    mismatches = [
        f"{field}: {actual!r} != {wanted!r}"
        for field, (actual, wanted) in comparisons.items()
        if actual != wanted
    ]
    if mismatches:
        raise RuntimeError(f"{code} lifecycle replay drift: {'; '.join(mismatches)}")


def run_backtest(
    start_date: str,
    end_date: str,
    output_dir: Path,
    *,
    execution_only: bool = False,
) -> dict[str, Any]:
    if not os.environ.get("TUSHARE_TOKEN"):
        raise RuntimeError("TUSHARE_TOKEN is required.")
    import tushare as ts

    pro = ts.pro_api(os.environ["TUSHARE_TOKEN"])
    overview = json.loads(OVERVIEW_PATH.read_text(encoding="utf-8"))
    specs_list = resolve_targets(overview)
    specs = {spec.code: spec for spec in specs_list}
    print(f"targets={len(specs_list)}", flush=True)

    benchmarks = {
        CORE_BENCHMARK: load_tushare_daily(
            pro, "index_daily", CORE_BENCHMARK, start_date, end_date
        ),
        HK_BENCHMARK: load_tushare_daily(
            pro, "index_global", HK_BENCHMARK, start_date, end_date
        ),
    }
    market_dates = benchmarks[CORE_BENCHMARK]["trade_date"].astype(str).tolist()
    market_amount = load_market_amount(pro, market_dates, start_date, end_date)

    signal_prices: dict[str, pd.DataFrame] = {}
    execution_prices: dict[str, pd.DataFrame | None] = {}
    snapshots_by_code: dict[str, list[dict[str, Any]]] = {}
    weight_frames: dict[str, pd.DataFrame] = {}
    for spec in specs_list:
        price_endpoint = "fund_daily" if spec.engine == "hk_proxy_partial" else "index_daily"
        signal_prices[spec.code] = load_tushare_daily(
            pro, price_endpoint, spec.price_code, start_date, end_date
        )
        execution_prices[spec.code] = (
            load_tushare_daily(pro, "fund_daily", spec.execution_code, start_date, end_date)
            if spec.execution_code
            else None
        )
        if spec.engine != "hk_proxy_partial":
            weights = load_index_weights(pro, spec.price_code, start_date, end_date)
            weight_frames[spec.code] = weights
            snapshots_by_code[spec.code] = build_snapshot_map(
                weights, hk_top_ten_only=spec.engine == "hk_connect"
            )
        else:
            snapshots_by_code[spec.code] = []
        print(f"prepared_target={spec.code}", flush=True)

    a_component_codes: set[str] = set()
    hk_component_codes: set[str] = set()
    for code, snapshots in snapshots_by_code.items():
        spec = specs[code]
        for snapshot in snapshots:
            selected = snapshot["topTen"] if spec.engine == "hk_connect" else snapshot["core"] + snapshot["topTen"]
            for item in selected:
                component_code = str(item["con_code"])
                if component_code.endswith(".HK"):
                    hk_component_codes.add(component_code)
                else:
                    a_component_codes.add(component_code)
    print(
        f"a_components={len(a_component_codes)} hk_components={len(hk_component_codes)}",
        flush=True,
    )

    a_components: dict[str, pd.DataFrame] = {}
    for offset, code in enumerate(sorted(a_component_codes), start=1):
        frame = load_tushare_daily(pro, "daily", code, start_date, end_date)
        if not frame.empty:
            a_components[code] = prepare_component_frame(frame)
        if offset % 50 == 0 or offset == len(a_component_codes):
            print(f"a_component_history={offset}/{len(a_component_codes)}", flush=True)
    hk_components: dict[str, pd.DataFrame] = {}
    for offset, code in enumerate(sorted(hk_component_codes), start=1):
        frame = load_tencent_hk_daily(code, start_date, end_date)
        if not frame.empty:
            hk_components[code] = prepare_component_frame(frame)
        if offset % 20 == 0 or offset == len(hk_component_codes):
            print(f"hk_component_history={offset}/{len(hk_component_codes)}", flush=True)

    histories: dict[str, pd.DataFrame] = {}
    for spec in specs_list:
        if spec.engine == "core":
            history = build_core_target_history(
                spec,
                signal_prices[spec.code],
                benchmarks[CORE_BENCHMARK],
                market_amount,
                snapshots_by_code[spec.code],
                a_components,
            )
        else:
            history = build_hk_target_history(
                spec,
                signal_prices[spec.code],
                snapshots_by_code[spec.code],
                hk_components,
            )
        validate_lifecycle_replay(signal_prices[spec.code], history, spec.code)
        histories[spec.code] = history
        print(f"replayed_target={spec.code} rows={len(history)}", flush=True)

    overview_by_code = {str(item["code"]): item for item in overview.get("targets", [])}
    if {
        item.get("latestDate") for item in overview.get("targets", [])
    } == {end_date}:
        label_mismatches = []
        for code, history in histories.items():
            if specs[code].engine == "hk_proxy_partial":
                continue
            expected_state = overview_by_code[code].get("maStateCode")
            if expected_state is None:
                continue
            actual_state = history.iloc[-1].get("state_code")
            if actual_state is None:
                actual_state = history.iloc[-1].get("primary_label")
            if actual_state != expected_state:
                label_mismatches.append(
                    f"{code}: replay={actual_state}, production={expected_state}"
                )
        if label_mismatches:
            raise RuntimeError(
                "Latest MA-state replay drift: " + "; ".join(label_mismatches)
            )

    execution_result = run_execution_grid(
        histories,
        execution_prices,
        specs,
        market_dates,
        benchmarks[CORE_BENCHMARK],
    )
    execution_paths = write_execution_outputs(
        output_dir, start_date, end_date, execution_result
    )
    for key, path in execution_paths.items():
        print(f"execution_{key}={path}", flush=True)
    if execution_only:
        return {"execution": execution_result, "paths": execution_paths}

    event_rows: list[dict[str, Any]] = []
    for code, history in histories.items():
        spec = specs[code]
        for event in extract_events(history):
            event_rows.append(
                add_forward_outcomes(
                    event,
                    signal_prices[code],
                    benchmarks[spec.benchmark_code],
                    execution_prices[code],
                )
            )
    baseline_rows = build_baseline_rows(histories, signal_prices, benchmarks, specs)
    summaries = summarize_event_rows(event_rows + baseline_rows)
    sensitivity = run_sensitivity(histories, signal_prices, benchmarks, specs)

    target_summary: list[dict[str, Any]] = []
    for code, history in histories.items():
        code_events = [row for row in event_rows if row["code"] == code]
        complete_dates = history.loc[history["structure_complete"], "trade_date"]
        target_summary.append(
            {
                "code": code,
                "name": specs[code].name,
                "engine": specs[code].engine,
                "firstPriceDate": str(signal_prices[code].iloc[0]["trade_date"]),
                "firstWeightDate": (
                    snapshots_by_code[code][0]["date"] if snapshots_by_code[code] else None
                ),
                "firstCompleteDate": str(complete_dates.iloc[0]) if not complete_dates.empty else None,
                "dailyRows": len(history),
                "labelEventCount": sum(row["eventType"].startswith("label_") for row in code_events),
                "initialStartCount": sum(row["eventType"] == "lifecycle_initial_start" for row in code_events),
                "trendConfirmationCount": sum(row["eventType"] == "lifecycle_trend_confirmation" for row in code_events),
                "startupConfirmationCount": sum(row["eventType"] == "label_启动确认" for row in code_events),
            }
        )

    meta = {
        "schemaVersion": "1.0",
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "startDate": start_date,
        "endDate": end_date,
        "targetCount": len(specs_list),
        "fullPrimaryReplayTargetCount": sum(
            spec.engine != "hk_proxy_partial" for spec in specs_list
        ),
        "partialReplayTargets": [
            spec.code for spec in specs_list if spec.engine == "hk_proxy_partial"
        ],
        "currentTargetUniverseSurvivorshipBias": True,
        "historicalWeightSnapshotsUsed": True,
        "lookaheadAllowed": False,
        "portfolioSimulation": False,
        "trueUntouchedOutOfSampleAvailable": False,
        "eventCount": len(event_rows),
    }
    result = {
        "meta": meta,
        "targetSummary": target_summary,
        "aggregate": summaries,
        "sensitivity": sensitivity,
        "limitations": [
            "Current 25-target universe creates target-selection survivorship bias.",
            "513970 has no historical official constituent snapshots and is partial only.",
            "2019-2023 is historical backcast, not a provably untouched out-of-sample set.",
            "No fees, market impact, or ETF premium/discount are included.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"etf_watch_backtest_{start_date}_{end_date}"
    json_path = output_dir / f"{stem}.json"
    events_path = output_dir / f"{stem}_events.csv"
    sensitivity_path = output_dir / f"{stem}_sensitivity.csv"
    report_path = output_dir / f"{stem}.md"
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    pd.DataFrame(event_rows).to_csv(events_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(sensitivity).to_csv(sensitivity_path, index=False, encoding="utf-8-sig")
    write_report(report_path, meta, summaries, target_summary, sensitivity)
    print(f"result_json={json_path}", flush=True)
    print(f"events_csv={events_path}", flush=True)
    print(f"sensitivity_csv={sensitivity_path}", flush=True)
    print(f"report_md={report_path}", flush=True)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Point-in-time ETF Watch signal backtest.")
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", default=DEFAULT_END_DATE)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument(
        "--execution-only",
        action="store_true",
        help="Write account-level execution-discipline outputs and skip signal sensitivity outputs.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.start_date > args.end_date:
        raise ValueError("start_date must not be after end_date.")
    run_backtest(
        args.start_date,
        args.end_date,
        args.output_dir,
        execution_only=args.execution_only,
    )


if __name__ == "__main__":
    main()

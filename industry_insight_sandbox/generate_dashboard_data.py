from __future__ import annotations

import argparse
import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

import pandas as pd
import tushare as ts


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
TOPIC_DIR = DATA_DIR / "topics"
TARGETS_PATH = ROOT / "targets.json"
HISTORY_START = "20240101"
CORE_WEIGHT_COVERAGE = 60.0
MAX_CORE_COUNT = 20
LEADER_WATCH_COUNT = 10
STRICT_LEADER_COUNT = 3
BENCHMARK_CODE = "000300.SH"
LOW_WARNING_DAYS = 40
LOW_PASS_DAYS = 60
FUNDING_CONFIRM_PERCENTILE = 0.80
CROWDING_HOT_PERCENTILE = 0.95


def as_float(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), 4)


def slug_for(code: str) -> str:
    return code.lower().replace(".", "-")


def safe_cache_name(value: str) -> str:
    return value.replace(".", "_").replace("/", "_")


def normalize_daily(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    frame = frame.copy()
    frame["trade_date"] = frame["trade_date"].astype(str)
    for column in ["open", "high", "low", "close", "pct_chg", "amount"]:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return (
        frame.drop_duplicates(subset=["trade_date"])
        .sort_values("trade_date")
        .reset_index(drop=True)
    )


def fetch_csv(
    cache_name: str,
    fetcher: Callable[[], pd.DataFrame],
    *,
    refresh: bool = False,
    retries: int = 3,
) -> pd.DataFrame:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{safe_cache_name(cache_name)}.csv"
    if path.exists() and not refresh:
        return pd.read_csv(path, dtype={"trade_date": str, "ts_code": str})

    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            frame = fetcher()
            frame.to_csv(path, index=False, encoding="utf-8-sig")
            return frame
        except Exception as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {cache_name}: {last_error}") from last_error


def fetch_market_amount_history(
    pro,
    trade_dates: list[str],
) -> pd.DataFrame:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / "market_amount_history.csv"
    if path.exists():
        history = pd.read_csv(path, dtype={"trade_date": str})
    else:
        history = pd.DataFrame(columns=["trade_date", "market_amount"])

    history["trade_date"] = history["trade_date"].astype(str)
    history["market_amount"] = pd.to_numeric(
        history["market_amount"], errors="coerce"
    )
    amount_by_date = history.set_index("trade_date")["market_amount"].to_dict()
    latest_date = trade_dates[-1]

    for index, trade_date in enumerate(trade_dates, start=1):
        if trade_date in amount_by_date and trade_date != latest_date:
            continue
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                daily = pro.daily(
                    trade_date=trade_date,
                    fields="trade_date,amount",
                )
                amount = pd.to_numeric(daily["amount"], errors="coerce").sum(
                    min_count=1
                )
                if pd.isna(amount):
                    raise RuntimeError(f"No market amount for {trade_date}.")
                amount_by_date[trade_date] = float(amount)
                break
            except Exception as exc:
                last_error = exc
                if attempt + 1 < 3:
                    time.sleep(2 * (attempt + 1))
        else:
            raise RuntimeError(
                f"Failed to fetch market amount for {trade_date}: {last_error}"
            ) from last_error
        time.sleep(0.12)
        if index % 25 == 0:
            print(f"  market amount history {index}/{len(trade_dates)}")

    result = pd.DataFrame(
        [
            {"trade_date": trade_date, "market_amount": amount_by_date[trade_date]}
            for trade_date in trade_dates
            if trade_date in amount_by_date
        ]
    )
    result.to_csv(path, index=False, encoding="utf-8-sig")
    return result


def limit_threshold(ts_code: str) -> float:
    bare = ts_code.split(".")[0]
    if bare.startswith(("688", "300")):
        return 19.5
    if bare.startswith(("8", "4")):
        return 29.5
    return 9.5


def condition(title: str, passed: bool, value: str, rule: str, note: str) -> dict:
    return {
        "title": title,
        "passed": bool(passed),
        "value": value,
        "rule": rule,
        "note": note,
    }


def build_topic(
    target: dict,
    info: dict,
    index_daily: pd.DataFrame,
    target_daily: pd.DataFrame,
    benchmark: pd.DataFrame,
    market_amount_history: pd.DataFrame,
    weights: pd.DataFrame,
    stock_histories: dict[str, pd.DataFrame],
    name_map: dict[str, str],
    industry_map: dict[str, str],
    market_map: dict[str, str],
) -> dict:
    index_daily = normalize_daily(index_daily)
    target_daily = normalize_daily(target_daily)
    latest_date = str(index_daily.iloc[-1]["trade_date"])
    weight_date = str(weights["trade_date"].max())
    weights = (
        weights[weights["trade_date"].astype(str) == weight_date]
        .copy()
        .sort_values("weight", ascending=False)
        .reset_index(drop=True)
    )
    weights["weight"] = pd.to_numeric(weights["weight"], errors="coerce")
    weights["cum_weight"] = weights["weight"].cumsum()
    coverage_count = int((weights["cum_weight"] < CORE_WEIGHT_COVERAGE).sum()) + 1
    core_count = min(max(3, coverage_count), MAX_CORE_COUNT, len(weights))
    core_weights = weights.head(core_count).copy()

    component_rows: list[dict] = []
    amount_frames: list[pd.DataFrame] = []
    usable_core_weights: list[float] = []

    for _, weight_row in core_weights.iterrows():
        code = str(weight_row["con_code"])
        daily = stock_histories.get(code)
        if daily is None or daily.empty:
            continue
        daily = daily.copy()
        daily["ma60"] = daily["close"].rolling(60).mean()
        daily["ma250"] = daily["close"].rolling(250).mean()
        latest = daily.iloc[-1]
        ret_5d = (
            float(latest["close"] / daily.iloc[-6]["close"] - 1)
            if len(daily) >= 6
            else None
        )
        ret_20d = (
            float(latest["close"] / daily.iloc[-21]["close"] - 1)
            if len(daily) >= 21
            else None
        )
        amount_ma20 = float(daily.tail(20)["amount"].mean()) if len(daily) >= 20 else None
        weight = float(weight_row["weight"])
        usable_core_weights.append(weight)
        amount_frames.append(
            daily[["trade_date", "amount"]].rename(columns={"amount": code})
        )
        component_rows.append(
            {
                "code": code,
                "name": str(name_map.get(code, code)),
                "industry": str(industry_map.get(code, "-")),
                "market": str(market_map.get(code, "-")),
                "weight": as_float(weight),
                "pct1d": as_float(latest["pct_chg"]),
                "ret5d": as_float(None if ret_5d is None else ret_5d * 100),
                "ret20d": as_float(None if ret_20d is None else ret_20d * 100),
                "aboveMa60": bool(
                    pd.notna(latest["ma60"]) and latest["close"] >= latest["ma60"]
                ),
                "aboveMa250": bool(
                    pd.notna(latest["ma250"]) and latest["close"] >= latest["ma250"]
                ),
                "amountRatio20": as_float(
                    None
                    if amount_ma20 in (None, 0)
                    else float(latest["amount"]) / amount_ma20
                ),
            }
        )

    if not component_rows or not amount_frames:
        raise RuntimeError(f"{target['code']} has no usable core component histories.")

    aggregate_amount = amount_frames[0]
    for frame in amount_frames[1:]:
        aggregate_amount = aggregate_amount.merge(frame, on="trade_date", how="outer")
    amount_columns = [column for column in aggregate_amount.columns if column != "trade_date"]
    aggregate_amount["core_amount"] = aggregate_amount[amount_columns].sum(axis=1, min_count=1)
    aggregate_amount = aggregate_amount[["trade_date", "core_amount"]].sort_values("trade_date")
    aggregate_amount["amount_ma20"] = aggregate_amount["core_amount"].rolling(20).mean()
    aggregate_amount["amount_ratio20"] = (
        aggregate_amount["core_amount"] / aggregate_amount["amount_ma20"]
    )

    index_daily["ma60"] = index_daily["close"].rolling(60).mean()
    index_daily["ma250"] = index_daily["close"].rolling(250).mean()
    index_daily = index_daily.merge(
        aggregate_amount[["trade_date", "core_amount", "amount_ratio20"]],
        on="trade_date",
        how="left",
    )
    index_daily = index_daily.merge(
        market_amount_history[["trade_date", "market_amount"]],
        on="trade_date",
        how="left",
    )
    index_daily["absorption_rate"] = (
        index_daily["amount"] / index_daily["market_amount"]
    )
    index_daily["absorption_rank_pct"] = (
        index_daily["absorption_rate"]
        .rolling(252, min_periods=120)
        .rank(pct=True)
    )
    latest = index_daily.iloc[-1]
    last_120 = index_daily.tail(120).copy()
    low_history = last_120.dropna(subset=["ma250"])
    below_ma250_10_days = int(
        (low_history["close"] <= low_history["ma250"] * 0.90).sum()
    )
    below_ma250_15_days = int(
        (low_history["close"] <= low_history["ma250"] * 0.85).sum()
    )
    low_history_complete = len(low_history) == 120
    structure_ok = low_history_complete and below_ma250_10_days >= LOW_PASS_DAYS
    structure_warning = (
        low_history_complete
        and LOW_WARNING_DAYS <= below_ma250_10_days < LOW_PASS_DAYS
    )

    aligned_relative = (
        index_daily[["trade_date", "close"]]
        .rename(columns={"close": "theme_close"})
        .merge(
            benchmark[["trade_date", "close"]].rename(
                columns={"close": "benchmark_close"}
            ),
            on="trade_date",
            how="inner",
        )
        .tail(121)
    )
    theme_ret_120 = float(
        aligned_relative.iloc[-1]["theme_close"]
        / aligned_relative.iloc[0]["theme_close"]
        - 1
    )
    benchmark_ret_120 = float(
        aligned_relative.iloc[-1]["benchmark_close"]
        / aligned_relative.iloc[0]["benchmark_close"]
        - 1
    )
    relative_excess = theme_ret_120 - benchmark_ret_120

    above_ma60 = bool(
        pd.notna(latest["ma60"]) and latest["close"] >= latest["ma60"]
    )
    ma60_streak = 0
    for _, row in index_daily.iloc[::-1].iterrows():
        if pd.isna(row["ma60"]) or row["close"] < row["ma60"]:
            break
        ma60_streak += 1
    ma60_watch_ok = above_ma60
    previous = index_daily.iloc[-2] if len(index_daily) >= 2 else None
    ma60_breakout_today = bool(
        previous is not None
        and pd.notna(previous["ma60"])
        and previous["close"] < previous["ma60"]
        and above_ma60
    )

    amount_ratio_latest = (
        float(latest["amount_ratio20"])
        if pd.notna(latest["amount_ratio20"])
        else 0.0
    )
    hold_two_days_ok = bool(
        index_daily.tail(2)["ma250"].notna().all()
        and (index_daily.tail(2)["close"] >= index_daily.tail(2)["ma250"]).all()
    )
    absorption_rank_latest = (
        float(latest["absorption_rank_pct"])
        if pd.notna(latest["absorption_rank_pct"])
        else None
    )
    last_three_funding_ranks = index_daily.tail(3)["absorption_rank_pct"]
    funding_confirmed = bool(
        last_three_funding_ranks.notna().all()
        and (last_three_funding_ranks >= FUNDING_CONFIRM_PERCENTILE).all()
    )
    crowding_hot = bool(
        absorption_rank_latest is not None
        and absorption_rank_latest >= CROWDING_HOT_PERCENTILE
    )
    crowding_overheated = bool(
        last_three_funding_ranks.notna().all()
        and (last_three_funding_ranks >= CROWDING_HOT_PERCENTILE).all()
    )
    breakout_emerged = hold_two_days_ok or funding_confirmed
    breakout_confirmed = hold_two_days_ok and funding_confirmed

    top_ten_weights = weights.head(LEADER_WATCH_COUNT).copy()
    top_ten_codes = top_ten_weights["con_code"].astype(str).tolist()
    top_three_codes = top_ten_codes[:STRICT_LEADER_COUNT]
    rank_map = {code: rank for rank, code in enumerate(top_ten_codes, start=1)}
    limit_events: list[dict] = []
    for code in top_ten_codes:
        daily = stock_histories.get(code)
        if daily is None or daily.empty:
            continue
        rank = rank_map[code]
        event_window = 5 if rank <= STRICT_LEADER_COUNT else 3
        recent = daily.tail(event_window).reset_index(drop=True)
        hits = recent.index[recent["pct_chg"] >= limit_threshold(code)].tolist()
        if not hits:
            continue
        hit_index = hits[-1]
        hit_close = float(recent.iloc[hit_index]["close"])
        next_day = recent.iloc[hit_index + 1] if hit_index + 1 < len(recent) else None
        latest_retained = float(daily.iloc[-1]["close"]) >= hit_close
        continuation_ok = bool(
            next_day is not None and float(next_day["pct_chg"]) > 0
        )
        limit_events.append(
            {
                "code": code,
                "name": str(name_map.get(code, code)),
                "weightRank": rank,
                "tier": "核心龙头" if rank <= STRICT_LEADER_COUNT else "权重异动",
                "date": str(recent.iloc[hit_index]["trade_date"]),
                "pct": as_float(recent.iloc[hit_index]["pct_chg"]),
                "continuationKnown": next_day is not None,
                "continuationPct": as_float(
                    None if next_day is None else next_day["pct_chg"]
                ),
                "continuationOk": continuation_ok,
                "latestRetained": latest_retained,
                "qualified": continuation_ok
                and (latest_retained if rank <= STRICT_LEADER_COUNT else True),
            }
        )

    strict_limit_events = [
        event
        for event in limit_events
        if event["weightRank"] <= STRICT_LEADER_COUNT
    ]
    strict_limit_ok = bool(strict_limit_events)
    strict_continuation_ok = any(event["qualified"] for event in strict_limit_events)
    secondary_limit_alert = any(
        event["weightRank"] > STRICT_LEADER_COUNT and event["qualified"]
        for event in limit_events
    )
    top_ten_limit_alert = strict_limit_ok or secondary_limit_alert
    active_count = sum(
        bool(
            (row["pct1d"] is not None and row["pct1d"] >= 5)
            or (row["ret5d"] is not None and row["ret5d"] >= 5)
        )
        for row in component_rows
    )
    ma60_count = sum(bool(row["aboveMa60"]) for row in component_rows)
    ma250_count = sum(bool(row["aboveMa250"]) for row in component_rows)
    leader_monitor_ok = (
        active_count >= 1 and ma60_count / len(component_rows) >= 0.5
    )
    leader_confirmed = strict_continuation_ok
    leader_warning = (top_ten_limit_alert or leader_monitor_ok) and not leader_confirmed

    close_to_high = float(latest["close"] / last_120["close"].max())
    trend_extension = bool(
        (pd.notna(latest["ma250"]) and latest["close"] > latest["ma250"] * 1.15)
        or relative_excess >= 0.15
        or (
            close_to_high >= 0.95
            and ma60_count / len(component_rows) >= 0.67
            and ma250_count / len(component_rows) >= 0.67
        )
    )

    if trend_extension:
        final_label = "趋势延续"
        conclusion = "指数与核心成分整体已脱离低位启动区，更适合按趋势延续与风险管理观察。"
    elif structure_ok and breakout_confirmed and leader_confirmed:
        final_label = "启动确认"
        conclusion = "低位结构、核心成分成交额、年线突破与权重龙头持续性已经闭环。"
    elif structure_ok and breakout_emerged and leader_monitor_ok:
        final_label = "接近启动"
        conclusion = "指数突破与核心成分开始共振，但站稳或龙头严格确认仍不完整。"
    elif (
        structure_ok
        or structure_warning
        or ma60_watch_ok
        or breakout_emerged
        or top_ten_limit_alert
        or leader_monitor_ok
    ):
        final_label = "观察中"
        conclusion = "已出现长期低位、MA60、资金集中或权重龙头异动线索，但三个核心条件尚未同时闭环。"
    else:
        final_label = "未启动"
        conclusion = "当前尚未形成低位结构、资金突破和权重龙头持续性的完整组合。"

    chart = index_daily.tail(320).copy()
    benchmark_chart = benchmark[["trade_date", "close"]].rename(
        columns={"close": "benchmark_close"}
    )
    chart = chart.merge(benchmark_chart, on="trade_date", how="left")
    chart["theme_normalized"] = chart["close"] / chart.iloc[0]["close"] * 100
    first_benchmark = chart["benchmark_close"].dropna().iloc[0]
    chart["benchmark_normalized"] = chart["benchmark_close"] / first_benchmark * 100

    ma250_gap = (
        float(latest["close"] / latest["ma250"] - 1)
        if pd.notna(latest["ma250"])
        else None
    )
    top_three_names = [
        str(name_map.get(code, code)) for code in top_three_codes
    ]
    top_ten_names = [
        str(name_map.get(code, code)) for code in top_ten_codes
    ]
    ma60_gap = (
        float(latest["close"] / latest["ma60"] - 1)
        if pd.notna(latest["ma60"])
        else None
    )

    return {
        "meta": {
            "generatedAt": pd.Timestamp.now(tz="Asia/Shanghai").strftime(
                "%Y-%m-%d %H:%M"
            ),
            "latestDate": latest_date,
            "weightDate": weight_date,
            "dataStart": str(index_daily.iloc[0]["trade_date"]),
            "method": "ETF/主题指数 + 指数权重核心成分股",
            "sandbox": True,
        },
        "target": {
            "slug": slug_for(target["code"]),
            "code": target["code"],
            "name": target["name"],
            "bucket": target["bucket"],
            "kind": target["kind"],
            "officialName": info["officialName"],
            "manager": info["manager"],
            "indexCode": info["indexCode"],
            "indexName": info["indexName"],
            "latestClose": as_float(target_daily.iloc[-1]["close"]),
            "latestPct": as_float(target_daily.iloc[-1]["pct_chg"]),
        },
        "summary": {
            "label": final_label,
            "conclusion": conclusion,
            "coreCount": len(component_rows),
            "coreCoverage": as_float(sum(usable_core_weights)),
            "activeCount": active_count,
            "aboveMa60Count": ma60_count,
            "aboveMa250Count": ma250_count,
            "strictLeaderConfirmed": leader_confirmed,
            "lowWarning": structure_warning,
            "belowMa250TenDays": below_ma250_10_days,
            "belowMa250FifteenDays": below_ma250_15_days,
            "ma60Watch": ma60_watch_ok,
            "ma60BreakoutToday": ma60_breakout_today,
            "ma60Gap": as_float(None if ma60_gap is None else ma60_gap * 100),
            "ma250Gap": as_float(None if ma250_gap is None else ma250_gap * 100),
            "amountRatio20": as_float(amount_ratio_latest),
            "absorptionRankPct": as_float(
                None
                if absorption_rank_latest is None
                else absorption_rank_latest * 100
            ),
            "fundingConfirmed": funding_confirmed,
            "crowdingHot": crowding_hot,
            "crowdingOverheated": crowding_overheated,
            "relativeExcess120": as_float(relative_excess * 100),
            "topThreeNames": top_three_names,
            "topTenNames": top_ten_names,
            "topTenLimitAlert": top_ten_limit_alert,
            "secondaryLimitAlert": secondary_limit_alert,
            "stagePassCount": sum([structure_ok, breakout_confirmed, leader_confirmed]),
        },
        "stages": [
            {
                "id": "structure",
                "number": "01",
                "title": "低位收敛",
                "subtitle": "120日低位停留时间",
                "passed": structure_ok,
                "warning": structure_warning,
                "items": [
                    condition(
                        "低位停留天数",
                        structure_ok,
                        f"{below_ma250_10_days}/120日",
                        "过去120日中，收盘低于MA250至少10%的天数 ≥ 60",
                        "达到40日先预警，达到60日正式通过。",
                    ),
                    condition(
                        "深度低位记录",
                        below_ma250_15_days > 0,
                        f"{below_ma250_15_days}/120日",
                        "展示低于MA250至少15%的天数，不作为硬性条件",
                        "用于区分低位停留的深度，不重复增加通过门槛。",
                    ),
                ],
            },
            {
                "id": "breakout",
                "number": "02",
                "title": "带量突破年线",
                "subtitle": "MA60预警，MA250确认",
                "passed": breakout_confirmed,
                "warning": ma60_watch_ok and not breakout_confirmed,
                "items": [
                    condition(
                        "MA60提前提示",
                        ma60_watch_ok,
                        (
                            "今日突破"
                            if ma60_breakout_today
                            else (
                                "-"
                                if pd.isna(latest["ma60"])
                                else f"站上{ma60_streak}日"
                            )
                        ),
                        "跟踪指数收盘站上MA60",
                        "只作为启动提前量提示，不替代MA250正式确认。",
                    ),
                    condition(
                        "连续站上年线",
                        hold_two_days_ok,
                        (
                            "-"
                            if pd.isna(latest["ma250"])
                            else f"{latest['close'] / latest['ma250'] - 1:.1%}"
                        ),
                        "最近2个交易日均收于MA250上方",
                        "取消3%幅度要求，用连续收盘过滤单日假突破。",
                    ),
                    condition(
                        "资金持续集中",
                        funding_confirmed,
                        (
                            "-"
                            if absorption_rank_latest is None
                            else f"{absorption_rank_latest:.0%}"
                        ),
                        "指数成交额占全A成交额的历史分位连续3日 ≥ 80%",
                        "使用过去252个交易日的自身历史分位判断增量资金。",
                    ),
                    condition(
                        "拥挤风险",
                        not crowding_hot,
                        (
                            "-"
                            if absorption_rank_latest is None
                            else f"{absorption_rank_latest:.0%}"
                        ),
                        "达到95%分位提示过热；连续3日达到95%视为高度拥挤",
                        "95%分位只做风险提示，不作为启动确认。",
                    ),
                ],
            },
            {
                "id": "leader",
                "number": "03",
                "title": "权重龙头确认",
                "subtitle": "前三闭环，第4至10名短期预警",
                "passed": leader_confirmed,
                "warning": leader_warning,
                "items": [
                    condition(
                        "观察对象明确",
                        len(top_ten_codes) == LEADER_WATCH_COUNT,
                        f"权重前{len(top_ten_codes)}",
                        "直接观察指数前10大权重股，而非申万市值龙头",
                        "权重前3用于严格确认，第4至10名用于渐进预警。",
                    ),
                    condition(
                        "次级龙头异动",
                        secondary_limit_alert,
                        f"{sum(event['weightRank'] > STRICT_LEADER_COUNT and event['qualified'] for event in limit_events)}次",
                        "权重第4至10名近3日涨停，且次日继续收红",
                        "只触发黄色预警，不能单独完成第三层闭环。",
                    ),
                    condition(
                        "前三龙头涨停",
                        strict_limit_ok,
                        f"{len(strict_limit_events)}次",
                        "权重前3近5日内至少一只触及涨停阈值",
                        "保留原策略对标志性龙头的严格要求。",
                    ),
                    condition(
                        "涨停后持续",
                        strict_continuation_ok,
                        "已确认" if strict_continuation_ok else "未确认",
                        "次日继续收红，且最新收盘不低于涨停日收盘",
                        "同时过滤单日脉冲和随后完全回吐。",
                    ),
                    condition(
                        "核心群体转强",
                        leader_monitor_ok,
                        f"{active_count}/{len(component_rows)} 活跃",
                        "至少1只明显转强，且≥50%核心成分站上MA60",
                        "这是监控辅助条件，不能替代严格龙头确认。",
                    ),
                ],
            },
        ],
        "chart": [
            {
                "date": str(row["trade_date"]),
                "close": as_float(row["close"]),
                "ma60": as_float(row["ma60"]),
                "ma250": as_float(row["ma250"]),
                "amountRatio20": as_float(row["amount_ratio20"]),
                "absorptionRankPct": as_float(
                    None
                    if pd.isna(row["absorption_rank_pct"])
                    else row["absorption_rank_pct"] * 100
                ),
                "themeNormalized": as_float(row["theme_normalized"]),
                "benchmarkNormalized": as_float(row["benchmark_normalized"]),
            }
            for _, row in chart.iterrows()
        ],
        "weights": [
            {
                "code": str(row["con_code"]),
                "name": str(name_map.get(str(row["con_code"]), row["con_code"])),
                "weight": as_float(row["weight"]),
                "industry": str(industry_map.get(str(row["con_code"]), "-")),
            }
            for _, row in weights.head(15).iterrows()
        ],
            "components": component_rows,
        "limitEvents": limit_events,
        "notes": [
            "这是封闭沙盒中的方法实验，不接入现有申万二级扫描、日报或发布流程。",
            "目标清单来自现有项目 theme_watch_config.py 的正式跟踪对象，并用 theme_watch_dashboard.py 补充分组和显示名称。",
            "指数权重采用最新可用月末数据；页面同时展示权重日期，防止前视偏差。",
            "申万二级只保留为行业归属和横向对照，不决定本专题的启动标签。",
            "资金集中度使用跟踪指数成交额占全A成交额的过去252日历史分位；80%用于确认，95%用于过热提示。",
        ],
    }


def main(end_date: str | None = None) -> None:
    token = ts.get_token()
    if not token:
        raise RuntimeError("Tushare token is not configured.")
    pro = ts.pro_api(token)
    targets = json.loads(TARGETS_PATH.read_text(encoding="utf-8"))
    if len(targets) != 20:
        raise RuntimeError(f"Expected 20 formal targets, found {len(targets)}.")

    end_date = end_date or date.today().strftime("%Y%m%d")
    try:
        as_of_date = datetime.strptime(end_date, "%Y%m%d").date()
    except ValueError as exc:
        raise ValueError("--end-date must use YYYYMMDD format.") from exc
    weight_start = (as_of_date - timedelta(days=210)).replace(day=1).strftime(
        "%Y%m%d"
    )
    weight_end = end_date

    etf_basic = fetch_csv(
        "etf_basic_active",
        lambda: pro.etf_basic(
            list_status="L",
            fields="ts_code,extname,cname,index_code,index_name,exchange,mgr_name",
        ),
        refresh=True,
    )
    stock_basic = fetch_csv(
        "stock_basic_active",
        lambda: pro.stock_basic(
            exchange="",
            list_status="L",
            fields="ts_code,name,industry,market",
        ),
        refresh=True,
    )
    etf_map = etf_basic.set_index("ts_code").to_dict("index")
    name_map = stock_basic.set_index("ts_code")["name"].to_dict()
    industry_map = stock_basic.set_index("ts_code")["industry"].to_dict()
    market_map = stock_basic.set_index("ts_code")["market"].to_dict()

    benchmark = normalize_daily(
        fetch_csv(
            f"index_daily_{BENCHMARK_CODE}_{HISTORY_START}_{end_date}",
            lambda: pro.index_daily(
                ts_code=BENCHMARK_CODE,
                start_date=HISTORY_START,
                end_date=end_date,
            ),
            refresh=True,
        )
    )
    market_trade_dates = (
        benchmark["trade_date"].astype(str).tail(260).tolist()
    )
    print(f"Preparing full-market amount history for {len(market_trade_dates)} days...")
    market_amount_history = fetch_market_amount_history(pro, market_trade_dates)

    prepared: list[dict] = []
    unique_component_codes: set[str] = set()
    print(f"Preparing {len(targets)} formal project targets...")

    for target in targets:
        code = target["code"]
        if target["kind"] == "etf":
            if code not in etf_map:
                raise RuntimeError(f"ETF basic info missing for formal target {code}.")
            etf = etf_map[code]
            info = {
                "officialName": str(etf.get("cname") or etf.get("extname") or target["name"]),
                "manager": str(etf.get("mgr_name") or "-"),
                "indexCode": str(etf["index_code"]),
                "indexName": str(etf["index_name"]),
            }
            target_daily = normalize_daily(
                fetch_csv(
                    f"fund_daily_{code}_{HISTORY_START}_{end_date}",
                    lambda code=code: pro.fund_daily(
                        ts_code=code,
                        start_date=HISTORY_START,
                        end_date=end_date,
                    ),
                    refresh=True,
                )
            )
        else:
            info = {
                "officialName": target["name"],
                "manager": "指数发布机构",
                "indexCode": code,
                "indexName": target["name"].replace("主题指数", "主题"),
            }
            target_daily = normalize_daily(
                fetch_csv(
                    f"index_daily_{code}_{HISTORY_START}_{end_date}",
                    lambda code=code: pro.index_daily(
                        ts_code=code,
                        start_date=HISTORY_START,
                        end_date=end_date,
                    ),
                    refresh=True,
                )
            )

        index_code = info["indexCode"]
        index_daily = (
            target_daily.copy()
            if target["kind"] == "index"
            else normalize_daily(
                fetch_csv(
                    f"index_daily_{index_code}_{HISTORY_START}_{end_date}",
                    lambda index_code=index_code: pro.index_daily(
                        ts_code=index_code,
                        start_date=HISTORY_START,
                        end_date=end_date,
                    ),
                    refresh=True,
                )
            )
        )
        weights = fetch_csv(
            f"index_weight_{index_code}_{weight_start}_{weight_end}",
            lambda index_code=index_code: pro.index_weight(
                index_code=index_code,
                start_date=weight_start,
                end_date=weight_end,
            ),
            refresh=True,
        )
        if target_daily.empty or index_daily.empty or weights.empty:
            raise RuntimeError(
                f"Formal target {code} has incomplete target/index/weight data."
            )
        weights["trade_date"] = weights["trade_date"].astype(str)
        weights["weight"] = pd.to_numeric(weights["weight"], errors="coerce")
        latest_weight_date = str(weights["trade_date"].max())
        latest_weights = (
            weights[weights["trade_date"] == latest_weight_date]
            .dropna(subset=["con_code", "weight"])
            .sort_values("weight", ascending=False)
            .reset_index(drop=True)
        )
        latest_weights["cum_weight"] = latest_weights["weight"].cumsum()
        coverage_count = (
            int((latest_weights["cum_weight"] < CORE_WEIGHT_COVERAGE).sum()) + 1
        )
        core_count = min(
            max(3, coverage_count), MAX_CORE_COUNT, len(latest_weights)
        )
        unique_component_codes.update(
            latest_weights.head(max(core_count, LEADER_WATCH_COUNT))["con_code"]
            .astype(str)
            .tolist()
        )
        prepared.append(
            {
                "target": target,
                "info": info,
                "target_daily": target_daily,
                "index_daily": index_daily,
                "weights": weights,
            }
        )
        print(
            f"  {code} -> {index_code} | weight_date={latest_weight_date} "
            f"| core={core_count}"
        )

    print(f"Fetching {len(unique_component_codes)} unique core component histories...")
    stock_histories: dict[str, pd.DataFrame] = {}
    for index, code in enumerate(sorted(unique_component_codes), start=1):
        daily = normalize_daily(
            fetch_csv(
                f"stock_daily_{code}_{HISTORY_START}_{end_date}",
                lambda code=code: pro.daily(
                    ts_code=code,
                    start_date=HISTORY_START,
                    end_date=end_date,
                ),
                refresh=True,
            )
        )
        if not daily.empty:
            stock_histories[code] = daily
        if index % 25 == 0 or index == len(unique_component_codes):
            print(f"  component histories {index}/{len(unique_component_codes)}")

    TOPIC_DIR.mkdir(parents=True, exist_ok=True)
    overview_rows: list[dict] = []
    topic_payloads: list[dict] = []
    for item in prepared:
        topic = build_topic(
            item["target"],
            item["info"],
            item["index_daily"],
            item["target_daily"],
            benchmark,
            market_amount_history,
            item["weights"],
            stock_histories,
            name_map,
            industry_map,
            market_map,
        )
        topic_payloads.append(topic)
        topic_path = TOPIC_DIR / f"{topic['target']['slug']}.json"
        topic_path.write_text(
            json.dumps(topic, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        overview_rows.append(
            {
                "slug": topic["target"]["slug"],
                "code": topic["target"]["code"],
                "name": topic["target"]["name"],
                "officialName": topic["target"]["officialName"],
                "bucket": topic["target"]["bucket"],
                "kind": topic["target"]["kind"],
                "indexCode": topic["target"]["indexCode"],
                "indexName": topic["target"]["indexName"],
                "label": topic["summary"]["label"],
                "conclusion": topic["summary"]["conclusion"],
                "latestDate": topic["meta"]["latestDate"],
                "weightDate": topic["meta"]["weightDate"],
                "latestPct": topic["target"]["latestPct"],
                "ma250Gap": topic["summary"]["ma250Gap"],
                "amountRatio20": topic["summary"]["amountRatio20"],
                "absorptionRankPct": topic["summary"]["absorptionRankPct"],
                "fundingConfirmed": topic["summary"]["fundingConfirmed"],
                "crowdingHot": topic["summary"]["crowdingHot"],
                "lowWarning": topic["summary"]["lowWarning"],
                "belowMa250TenDays": topic["summary"]["belowMa250TenDays"],
                "relativeExcess120": topic["summary"]["relativeExcess120"],
                "coreCount": topic["summary"]["coreCount"],
                "coreCoverage": topic["summary"]["coreCoverage"],
                "activeCount": topic["summary"]["activeCount"],
                "aboveMa60Count": topic["summary"]["aboveMa60Count"],
                "aboveMa250Count": topic["summary"]["aboveMa250Count"],
                "ma60Watch": topic["summary"]["ma60Watch"],
                "ma60BreakoutToday": topic["summary"]["ma60BreakoutToday"],
                "topTenLimitAlert": topic["summary"]["topTenLimitAlert"],
                "secondaryLimitAlert": topic["summary"]["secondaryLimitAlert"],
                "stagePassCount": topic["summary"]["stagePassCount"],
                "stageStates": [
                    {
                        "title": stage["title"],
                        "passed": stage["passed"],
                        "warning": stage["warning"],
                    }
                    for stage in topic["stages"]
                ],
                "topThreeNames": topic["summary"]["topThreeNames"],
                "order": item["target"]["order"],
            }
        )
        print(
            f"Wrote {topic_path.name} | label={topic['summary']['label']} "
            f"| components={topic['summary']['coreCount']}"
        )

    overview_rows.sort(key=lambda row: (row["bucket"], row["order"]))
    overview = {
        "meta": {
            "generatedAt": pd.Timestamp.now(tz="Asia/Shanghai").strftime(
                "%Y-%m-%d %H:%M"
            ),
            "targetCount": len(overview_rows),
            "etfCount": sum(row["kind"] == "etf" for row in overview_rows),
            "indexCount": sum(row["kind"] == "index" for row in overview_rows),
            "source": "现有项目 theme_watch_config.py THEME_DAILIES + theme_watch_dashboard.py BASE_CARDS",
            "sandbox": True,
        },
        "targets": overview_rows,
    }
    (DATA_DIR / "overview.json").write_text(
        json.dumps(overview, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (DATA_DIR / "all_topics.json").write_text(
        json.dumps(topic_payloads, ensure_ascii=False),
        encoding="utf-8",
    )
    print(
        f"Completed {len(overview_rows)} topics: "
        f"{overview['meta']['etfCount']} ETFs + {overview['meta']['indexCount']} index."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate ETF/index constituent observation datasets."
    )
    parser.add_argument(
        "--end-date",
        default=date.today().strftime("%Y%m%d"),
        help="Data cutoff in YYYYMMDD format.",
    )
    main(parser.parse_args().end_date)

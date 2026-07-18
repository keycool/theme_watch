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


def rolling_range(frame: pd.DataFrame) -> float:
    mean_close = float(frame["close"].mean())
    if not mean_close:
        return 0.0
    return float((frame["high"].max() - frame["low"].min()) / mean_close)


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
    latest = index_daily.iloc[-1]
    last_120 = index_daily.tail(120).copy()
    first_80 = last_120.head(80)
    last_40 = last_120.tail(40)

    distance_120d_high = float(latest["close"] / last_120["close"].max() - 1)
    low_zone_ok = distance_120d_high <= -0.15
    contraction_ratio = rolling_range(last_40) / rolling_range(first_80)
    contraction_ok = contraction_ratio <= 0.90
    no_new_low_ratio = float(last_40["close"].min() / last_120["close"].min())
    no_new_low_ok = no_new_low_ratio >= 1.02

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
    relative_cold_ok = relative_excess <= -0.05
    structure_ok = all(
        [low_zone_ok, contraction_ok, no_new_low_ok, relative_cold_ok]
    )

    above_ma60 = bool(
        pd.notna(latest["ma60"]) and latest["close"] >= latest["ma60"]
    )
    ma60_streak = 0
    for _, row in index_daily.iloc[::-1].iterrows():
        if pd.isna(row["ma60"]) or row["close"] < row["ma60"]:
            break
        ma60_streak += 1
    ma60_watch_ok = above_ma60 and ma60_streak <= 20
    previous = index_daily.iloc[-2] if len(index_daily) >= 2 else None
    ma60_breakout_today = bool(
        previous is not None
        and pd.notna(previous["ma60"])
        and previous["close"] < previous["ma60"]
        and above_ma60
    )

    above_ma250_3pct = bool(
        pd.notna(latest["ma250"]) and latest["close"] >= latest["ma250"] * 1.03
    )
    amount_ratio_latest = (
        float(latest["amount_ratio20"])
        if pd.notna(latest["amount_ratio20"])
        else 0.0
    )
    volume_ok = amount_ratio_latest >= 1.20
    hold_two_days_ok = bool(
        index_daily.tail(2)["ma250"].notna().all()
        and (index_daily.tail(2)["close"] >= index_daily.tail(2)["ma250"]).all()
    )
    breakout_streak = 0
    for _, row in index_daily.iloc[::-1].iterrows():
        if pd.isna(row["ma250"]) or row["close"] < row["ma250"] * 1.03:
            break
        breakout_streak += 1
    new_breakout_ok = breakout_streak <= 20
    breakout_emerged = above_ma250_3pct and volume_ok and new_breakout_ok
    breakout_confirmed = breakout_emerged and hold_two_days_ok

    top_ten_weights = weights.head(LEADER_WATCH_COUNT).copy()
    top_ten_codes = top_ten_weights["con_code"].astype(str).tolist()
    top_three_codes = top_ten_codes[:STRICT_LEADER_COUNT]
    rank_map = {code: rank for rank, code in enumerate(top_ten_codes, start=1)}
    limit_events: list[dict] = []
    for code in top_ten_codes:
        daily = stock_histories.get(code)
        if daily is None or daily.empty:
            continue
        recent = daily.tail(20).reset_index(drop=True)
        hits = recent.index[recent["pct_chg"] >= limit_threshold(code)].tolist()
        if not hits:
            continue
        hit_index = hits[-1]
        next_day = recent.iloc[hit_index + 1] if hit_index + 1 < len(recent) else None
        limit_events.append(
            {
                "code": code,
                "name": str(name_map.get(code, code)),
                "weightRank": rank_map[code],
                "tier": "核心龙头" if rank_map[code] <= STRICT_LEADER_COUNT else "权重异动",
                "date": str(recent.iloc[hit_index]["trade_date"]),
                "pct": as_float(recent.iloc[hit_index]["pct_chg"]),
                "continuationKnown": next_day is not None,
                "continuationPct": as_float(
                    None if next_day is None else next_day["pct_chg"]
                ),
                "continuationOk": bool(
                    next_day is not None and float(next_day["pct_chg"]) > 0
                ),
            }
        )

    strict_limit_events = [
        event
        for event in limit_events
        if event["weightRank"] <= STRICT_LEADER_COUNT
    ]
    strict_limit_ok = bool(strict_limit_events)
    strict_continuation_ok = any(
        event["continuationOk"] for event in strict_limit_events
    )
    top_ten_limit_alert = bool(limit_events)
    secondary_limit_alert = any(
        event["weightRank"] > STRICT_LEADER_COUNT for event in limit_events
    )
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
    leader_confirmed = strict_limit_ok and strict_continuation_ok
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
        or ma60_watch_ok
        or breakout_emerged
        or top_ten_limit_alert
        or leader_monitor_ok
    ):
        final_label = "观察中"
        conclusion = "已出现MA60、前十大权重异动或其他局部转强线索，但三个核心条件尚未同时闭环。"
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
            "ma60Watch": ma60_watch_ok,
            "ma60BreakoutToday": ma60_breakout_today,
            "ma60Gap": as_float(None if ma60_gap is None else ma60_gap * 100),
            "ma250Gap": as_float(None if ma250_gap is None else ma250_gap * 100),
            "amountRatio20": as_float(amount_ratio_latest),
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
                "subtitle": "四项量化标准同时通过",
                "passed": structure_ok,
                "warning": False,
                "items": [
                    condition(
                        "仍处低位",
                        low_zone_ok,
                        f"{distance_120d_high:.1%}",
                        "距120日高点 ≤ -15%",
                        "避免把已接近阶段高点的对象当作低位启动。",
                    ),
                    condition(
                        "波动收敛",
                        contraction_ok,
                        f"{contraction_ratio:.2f}×",
                        "后40日区间 / 前80日区间 ≤ 0.90",
                        "用日线代理周线高点降低、低点抬高的收敛过程。",
                    ),
                    condition(
                        "停止创新低",
                        no_new_low_ok,
                        f"{no_new_low_ratio:.3f}×",
                        "40日低点 / 120日低点 ≥ 1.02",
                        "确认抛压释放后低点开始抬高。",
                    ),
                    condition(
                        "相对冷门",
                        relative_cold_ok,
                        f"{relative_excess:.1%}",
                        "120日相对沪深300超额 ≤ -5%",
                        "用宽基超额收益统一比较不同ETF和主题指数的冷热。",
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
                        "跟踪指数收于MA60上方，且连续天数 ≤ 20",
                        "只作为启动提前量提示，不替代MA250正式确认。",
                    ),
                    condition(
                        "有效越过年线",
                        above_ma250_3pct,
                        (
                            "-"
                            if pd.isna(latest["ma250"])
                            else f"{latest['close'] / latest['ma250'] - 1:.1%}"
                        ),
                        "跟踪指数收盘 ≥ MA250 × 1.03",
                        "ETF专题判断跟踪指数；主题指数直接判断自身。",
                    ),
                    condition(
                        "核心成分放量",
                        volume_ok,
                        f"{amount_ratio_latest:.2f}×",
                        "核心成分合计成交额 ≥ 20日均值 × 1.20",
                        "不使用ETF自身成交额，避免申赎和交易活跃度干扰。",
                    ),
                    condition(
                        "突破后站稳",
                        hold_two_days_ok,
                        "2日" if hold_two_days_ok else "未站稳",
                        "最近2个交易日均收于MA250上方",
                        "排除盘中冲高和单日假突破。",
                    ),
                    condition(
                        "属于新突破",
                        new_breakout_ok,
                        f"{breakout_streak}日",
                        "高于MA250 3%的连续天数 ≤ 20",
                        "避免把已经充分上涨的趋势段标为首次启动。",
                    ),
                ],
            },
            {
                "id": "leader",
                "number": "03",
                "title": "权重龙头确认",
                "subtitle": "前10预警，前3严格确认",
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
                        "前十大涨停预警",
                        top_ten_limit_alert,
                        f"{len(limit_events)}次",
                        "前10大权重股近20日内任一只触及涨停阈值",
                        "第4至10名涨停会提示，但不会单独形成严格确认。",
                    ),
                    condition(
                        "前三龙头涨停",
                        strict_limit_ok,
                        f"{len(strict_limit_events)}次",
                        "权重前3近20日内至少一只触及涨停阈值",
                        "保留原策略对标志性龙头的严格要求。",
                    ),
                    condition(
                        "涨停后延续",
                        strict_continuation_ok,
                        "已确认" if strict_continuation_ok else "未确认",
                        "涨停后的下一交易日继续收红",
                        "用于区分市场共识和单日脉冲。",
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

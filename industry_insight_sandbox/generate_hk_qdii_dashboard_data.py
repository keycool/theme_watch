from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from moving_average_lifecycle import evaluate_moving_average_lifecycle


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "data" / "hk_qdii" / "513970-sh.json"
ETF_CODE = "513970.SH"
INDEX_CODE = "02018.00"
INDEX_VENDOR_CODE = "HSCGSI"
BENCHMARK_CODE = "HSI"
HISTORY_START = "20230101"
LOW_BELOW_MA250_WARNING_DAYS = 40
LOW_BELOW_MA250_PASS_DAYS = 60
LOW_DEEP_10_WARNING_DAYS = 12
LOW_DEEP_10_PASS_DAYS = 24
FUNDING_CONFIRM_PERCENTILE = 0.80
CROWDING_HOT_PERCENTILE = 0.95
LEADER_ABSOLUTE_RETURN = 5.0
LEADER_RETURN_PERCENTILE = 0.95
OFFICIAL_CONSTITUENT_URL = (
    "https://www.hsi.com.hk/api/wsit-hsil-hiip-ea-public-proxy/"
    "v1/dataretrieval/e/constituents/v1"
)
TENCENT_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"

CHINESE_NAMES = {
    "00669": "创科实业",
    "09992": "泡泡玛特",
    "09987": "百胜中国",
    "02020": "安踏体育",
    "09633": "农夫山泉",
    "00288": "万洲国际",
    "00300": "美的集团",
    "02319": "蒙牛乳业",
    "06690": "海尔智家",
    "00291": "华润啤酒",
}


def as_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), 4)


def compact_date(value: str) -> str:
    return str(value).replace("-", "")[:8]


def normalize_daily(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    result = frame.copy()
    result["trade_date"] = result["trade_date"].astype(str).map(compact_date)
    for column in ["open", "high", "low", "close", "pct_chg", "amount", "volume"]:
        if column in result:
            result[column] = pd.to_numeric(result[column], errors="coerce")
    result = (
        result.dropna(subset=["trade_date", "close"])
        .drop_duplicates(subset=["trade_date"], keep="last")
        .sort_values("trade_date")
        .reset_index(drop=True)
    )
    if "pct_chg" not in result or result["pct_chg"].isna().all():
        result["pct_chg"] = result["close"].pct_change() * 100
    result["ma20"] = result["close"].rolling(20).mean()
    result["ma60"] = result["close"].rolling(60).mean()
    result["ma250"] = result["close"].rolling(250).mean()
    return result


def evaluate_low_position(
    *,
    below_ma250_days: int,
    below_ma250_ten_days: int,
) -> dict[str, bool]:
    passed = (
        below_ma250_days >= LOW_BELOW_MA250_PASS_DAYS
        or below_ma250_ten_days >= LOW_DEEP_10_PASS_DAYS
    )
    warning = not passed and (
        below_ma250_days >= LOW_BELOW_MA250_WARNING_DAYS
        or below_ma250_ten_days >= LOW_DEEP_10_WARNING_DAYS
    )
    return {"passed": passed, "warning": warning}


def evaluate_short_term_rhythm(daily: pd.DataFrame) -> str:
    if len(daily) < 6:
        return "震荡整理"

    latest = daily.iloc[-1]
    five_days_ago = daily.iloc[-6]
    values = [
        latest.get("close"),
        latest.get("ma20"),
        latest.get("ma60"),
        five_days_ago.get("ma20"),
    ]
    if any(pd.isna(value) for value in values):
        return "震荡整理"

    close = float(latest["close"])
    ma20 = float(latest["ma20"])
    ma60 = float(latest["ma60"])
    ma20_rising = ma20 > float(five_days_ago["ma20"])

    if close >= ma20 and ma20 >= ma60 and ma20_rising:
        return "短期转强"
    if close >= ma20 and ma20 < ma60:
        return "低位反弹"
    if close < ma20 and ma20 >= ma60 and ma20_rising:
        return "上升回踩"
    if close < ma20 and not ma20_rising:
        return "短期转弱"
    return "震荡整理"


def evaluate_hk_breadth(component_rows: list[dict[str, Any]]) -> dict[str, Any]:
    fresh_rows = [row for row in component_rows if row["dataFresh"]]
    above_ma60_count = sum(row["aboveMa60"] for row in fresh_rows)
    positive_5d_count = sum((row["ret5d"] or 0) > 0 for row in fresh_rows)
    return {
        "freshCount": len(fresh_rows),
        "aboveMa60Count": above_ma60_count,
        "positive5dCount": positive_5d_count,
        "confirmed": bool(
            len(fresh_rows) == 10
            and above_ma60_count >= 5
            and positive_5d_count >= 5
        ),
    }


def evaluate_hk_leader_event(
    *,
    code: str,
    name: str,
    rank: int,
    as_of: str,
    daily: pd.DataFrame,
    market_trade_dates: list[str] | None = None,
) -> dict[str, Any] | None:
    eligible = normalize_daily(daily)
    eligible = eligible[eligible["trade_date"] <= as_of].copy()
    if eligible.empty:
        return None

    component_latest_date = str(eligible.iloc[-1]["trade_date"])
    data_fresh = component_latest_date == as_of
    eligible["returnP95"] = (
        eligible["pct_chg"]
        .rolling(120, min_periods=60)
        .quantile(LEADER_RETURN_PERCENTILE)
        .shift(1)
    )
    event_window = 5 if rank <= 3 else 3
    if market_trade_dates:
        window_dates = [
            value for value in market_trade_dates if value <= as_of
        ][-event_window:]
        window = eligible[eligible["trade_date"].isin(window_dates)].copy()
    else:
        window = eligible.tail(event_window).copy()
    if window.empty:
        return None

    threshold = window["returnP95"].fillna(LEADER_ABSOLUTE_RETURN).clip(
        lower=LEADER_ABSOLUTE_RETURN
    )
    hits = window[window["pct_chg"] >= threshold]
    if hits.empty:
        return None

    event_row = hits.iloc[-1]
    event_position = eligible.index[eligible["trade_date"] == event_row["trade_date"]]
    if event_position.empty:
        return None
    position = int(event_position[-1])
    continuation = eligible.iloc[position + 1] if position + 1 < len(eligible) else None
    continuation_known = continuation is not None
    continuation_pct = (
        float(continuation["pct_chg"]) if continuation_known else None
    )
    continuation_ok = bool(
        continuation_known
        and continuation_pct is not None
        and continuation_pct > 0
    )
    latest_retained = bool(
        float(eligible.iloc[-1]["close"]) >= float(event_row["close"])
    )
    qualified = bool(
        data_fresh and continuation_ok and latest_retained
    )

    return {
        "code": code,
        "name": name,
        "rank": rank,
        "tier": "前三龙头" if rank <= 3 else "次级权重",
        "date": str(event_row["trade_date"]),
        "pct": as_float(event_row["pct_chg"]),
        "dynamicThreshold": as_float(
            max(LEADER_ABSOLUTE_RETURN, float(event_row["returnP95"]))
            if pd.notna(event_row["returnP95"])
            else LEADER_ABSOLUTE_RETURN
        ),
        "componentLatestDate": component_latest_date,
        "dataFresh": data_fresh,
        "continuationDate": (
            str(continuation["trade_date"]) if continuation_known else None
        ),
        "continuationPct": as_float(continuation_pct),
        "continuationOk": continuation_ok,
        "latestRetained": latest_retained,
        "qualified": qualified,
        "strictQualified": bool(rank <= 3 and qualified),
    }


def fetch_json(url: str, params: dict[str, str]) -> dict[str, Any]:
    request = Request(
        f"{url}?{urlencode(params)}",
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 Industry-Insight/1.0",
        },
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_official_constituents() -> tuple[str, list[dict[str, Any]]]:
    payload = fetch_json(
        OFFICIAL_CONSTITUENT_URL,
        {"language": "eng", "indexCode": INDEX_CODE},
    )
    data = payload.get("data")
    if payload.get("code") != 200 or not data:
        raise RuntimeError("恒生指数公司未返回恒生消费前十大成分股。")
    rows = []
    for item in sorted(data["constituents"], key=lambda value: value["weightOrder"]):
        bare_code = str(item["stockCode"]).zfill(5)
        rows.append(
            {
                "code": f"{bare_code}.HK",
                "quoteCode": f"hk{bare_code}",
                "name": CHINESE_NAMES.get(bare_code, item["stockName"]),
                "englishName": item["stockName"],
                "rank": int(item["weightOrder"]),
            }
        )
    if len(rows) != 10:
        raise RuntimeError(f"恒生消费前十大成分股数量异常：{len(rows)}。")
    return compact_date(data["tradeDate"]), rows


def fetch_tencent_daily(quote_code: str) -> pd.DataFrame:
    payload = fetch_json(
        TENCENT_KLINE_URL,
        {"param": f"{quote_code},day,,,400,qfq"},
    )
    stock = payload.get("data", {}).get(quote_code, {})
    rows = stock.get("day")
    if not rows:
        raise RuntimeError(f"腾讯行情未返回 {quote_code} 日线。")
    return pd.DataFrame(
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


def rolling_percentile(series: pd.Series, window: int = 252) -> pd.Series:
    return series.rolling(window, min_periods=60).apply(
        lambda values: pd.Series(values).rank(pct=True).iloc[-1],
        raw=False,
    )


def return_over_period(frame: pd.DataFrame, periods: int) -> float | None:
    if len(frame) <= periods:
        return None
    return as_float((frame.iloc[-1]["close"] / frame.iloc[-periods - 1]["close"] - 1) * 100)


def stage_item(
    title: str,
    passed: bool,
    value: str,
    rule: str,
    note: str,
) -> dict[str, Any]:
    return {
        "title": title,
        "passed": passed,
        "value": value,
        "rule": rule,
        "note": note,
    }


def build_dashboard(pro: Any, requested_end_date: str) -> dict[str, Any]:
    official_date, constituents = fetch_official_constituents()
    fund = normalize_daily(
        pro.fund_daily(
            ts_code=ETF_CODE,
            start_date=HISTORY_START,
            end_date=requested_end_date,
            fields="ts_code,trade_date,open,high,low,close,pct_chg,amount",
        )
    )
    benchmark = normalize_daily(
        pro.index_global(
            ts_code=BENCHMARK_CODE,
            start_date=HISTORY_START,
            end_date=requested_end_date,
            fields="ts_code,trade_date,open,high,low,close,pct_chg",
        )
    )
    if len(fund) < 370:
        raise RuntimeError(f"{ETF_CODE} 日线不足：{len(fund)}。")
    if benchmark.empty:
        raise RuntimeError("恒生指数基准行情为空。")

    component_frames: dict[str, pd.DataFrame] = {}
    for component in constituents:
        frame = normalize_daily(fetch_tencent_daily(component["quoteCode"]))
        frame = frame[frame["trade_date"] <= requested_end_date].copy()
        if len(frame) < 250:
            raise RuntimeError(f"{component['code']} 日线不足：{len(frame)}。")
        component_frames[component["code"]] = frame

    as_of = min(
        str(fund.iloc[-1]["trade_date"]),
        str(benchmark.iloc[-1]["trade_date"]),
    )
    fund = fund[fund["trade_date"] <= as_of].copy()
    benchmark = benchmark[benchmark["trade_date"] <= as_of].copy()
    component_frames = {
        code: frame[frame["trade_date"] <= as_of].copy()
        for code, frame in component_frames.items()
    }

    fund["amountRank"] = rolling_percentile(fund["amount"])
    fund["amountMa20Ratio"] = fund["amount"] / fund["amount"].rolling(20).mean()
    last_120 = fund.dropna(subset=["ma250"]).tail(120)
    if len(last_120) != 120:
        raise RuntimeError("ETF 不足以计算完整的 120 日低位窗口。")
    below_ma250_days = int((last_120["close"] < last_120["ma250"]).sum())
    below_ma250_ten_days = int(
        (last_120["close"] <= last_120["ma250"] * 0.90).sum()
    )
    below_ma250_fifteen_days = int(
        (last_120["close"] <= last_120["ma250"] * 0.85).sum()
    )
    low_state = evaluate_low_position(
        below_ma250_days=below_ma250_days,
        below_ma250_ten_days=below_ma250_ten_days,
    )

    latest = fund.iloc[-1]
    previous = fund.iloc[-2]
    rhythm_label = evaluate_short_term_rhythm(fund)
    ma_lifecycle = evaluate_moving_average_lifecycle(fund)
    ma60_above = bool(latest["close"] > latest["ma60"])
    ma60_breakout_today = bool(
        latest["close"] > latest["ma60"]
        and previous["close"] <= previous["ma60"]
    )
    ma250_confirmed = bool(
        latest["close"] > latest["ma250"]
        and previous["close"] > previous["ma250"]
    )
    last_three_ranks = fund["amountRank"].tail(3)
    funding_confirmed = bool(
        last_three_ranks.notna().all()
        and (last_three_ranks >= FUNDING_CONFIRM_PERCENTILE).all()
    )
    crowding_hot = bool(
        pd.notna(latest["amountRank"])
        and latest["amountRank"] >= CROWDING_HOT_PERCENTILE
    )
    breakout_passed = ma250_confirmed and funding_confirmed
    breakout_warning = not breakout_passed and (
        ma60_above or ma250_confirmed or funding_confirmed
    )

    market_trade_dates = [
        str(value) for value in benchmark["trade_date"].tail(10)
    ]
    component_rows = []
    leader_events = []
    for component in constituents:
        frame = component_frames[component["code"]].copy()
        frame["volumeRatio20"] = frame["volume"] / frame["volume"].rolling(20).mean()
        row = frame.iloc[-1]
        ret_5d = return_over_period(frame, 5)
        ret_20d = return_over_period(frame, 20)
        component_rows.append(
            {
                "code": component["code"],
                "name": component["name"],
                "englishName": component["englishName"],
                "rank": component["rank"],
                "weight": None,
                "latestDate": str(row["trade_date"]),
                "dataFresh": str(row["trade_date"]) == as_of,
                "latestClose": as_float(row["close"]),
                "pct1d": as_float(row["pct_chg"]),
                "ret5d": ret_5d,
                "ret20d": ret_20d,
                "aboveMa60": bool(row["close"] > row["ma60"]),
                "aboveMa250": bool(row["close"] > row["ma250"]),
                "volumeRatio20": as_float(row["volumeRatio20"]),
            }
        )
        event = evaluate_hk_leader_event(
            code=component["code"],
            name=component["name"],
            rank=component["rank"],
            as_of=as_of,
            daily=frame,
            market_trade_dates=market_trade_dates,
        )
        if event:
            leader_events.append(event)

    breadth = evaluate_hk_breadth(component_rows)
    above_ma60_count = breadth["aboveMa60Count"]
    positive_5d_count = breadth["positive5dCount"]
    breadth_confirmed = breadth["confirmed"]
    strict_leader_confirmed = any(
        event["strictQualified"] for event in leader_events
    )
    secondary_alert = any(
        event["qualified"] and event["rank"] > 3 for event in leader_events
    )
    leader_passed = strict_leader_confirmed and breadth_confirmed
    leader_warning = not leader_passed and (
        strict_leader_confirmed or secondary_alert or breadth_confirmed
    )

    stage_pass_count = sum(
        [low_state["passed"], breakout_passed, leader_passed]
    )
    if stage_pass_count == 3:
        label = "启动确认"
        conclusion = "低位、价格与资金、权重龙头三层条件已经闭环。"
    elif low_state["passed"] and breakout_passed and leader_warning:
        label = "接近启动"
        conclusion = "低位与量价条件已完成，等待前三权重龙头及群体广度共同确认。"
    elif (
        stage_pass_count
        or low_state["warning"]
        or breakout_warning
        or leader_warning
    ):
        label = "观察中"
        clues = []
        if low_state["passed"]:
            clues.append("低位条件通过")
        elif low_state["warning"]:
            clues.append("低位提前预警")
        if ma60_above:
            clues.append("站上MA60")
        if funding_confirmed:
            clues.append("ETF资金分位达标")
        if leader_warning:
            clues.append("权重成分出现转强线索")
        conclusion = f"当前线索：{'、'.join(clues) or '尚未形成明确闭环'}。"
    else:
        label = "未启动"
        conclusion = "低位、量价与权重龙头尚未形成可验证的启动链路。"

    chart = fund.tail(400)[
        [
            "trade_date",
            "close",
            "ma20",
            "ma60",
            "ma250",
            "amountRank",
        ]
    ].merge(
        benchmark[["trade_date", "close"]].rename(
            columns={"close": "benchmarkClose"}
        ),
        on="trade_date",
        how="left",
    )
    first_etf = float(chart.iloc[0]["close"])
    first_benchmark = chart["benchmarkClose"].dropna().iloc[0]
    chart["etfNormalized"] = chart["close"] / first_etf * 100
    chart["benchmarkNormalized"] = (
        chart["benchmarkClose"] / first_benchmark * 100
    )

    ma60_gap = (latest["close"] / latest["ma60"] - 1) * 100
    ma250_gap = (latest["close"] / latest["ma250"] - 1) * 100
    stages = [
        {
            "id": "structure",
            "number": "01",
            "title": "低位收敛",
            "subtitle": "ETF价格代理长期位置",
            **low_state,
            "items": [
                stage_item(
                    "年线下停留",
                    below_ma250_days >= LOW_BELOW_MA250_PASS_DAYS,
                    f"{below_ma250_days}/120日",
                    "过去120日中，ETF收盘低于MA250的天数 ≥ 60",
                    "达到40日先预警；使用ETF价格代理恒生消费指数长期位置。",
                ),
                stage_item(
                    "加速下跌记录",
                    below_ma250_ten_days >= LOW_DEEP_10_PASS_DAYS,
                    f"{below_ma250_ten_days}/120日",
                    "过去120日中，ETF收盘低于MA250至少10%的天数 ≥ 24",
                    "达到12日先预警；两条低位路径满足其一即可。",
                ),
                stage_item(
                    "深度低位记录",
                    False,
                    f"{below_ma250_fifteen_days}/120日",
                    "展示ETF低于MA250至少15%的天数，不作为硬条件",
                    "用于描述低位深度。",
                ),
            ],
        },
        {
            "id": "breakout",
            "number": "02",
            "title": "量价趋势确认",
            "subtitle": "MA60预警，MA250与ETF资金确认",
            "passed": breakout_passed,
            "warning": breakout_warning,
            "items": [
                stage_item(
                    "MA60提前提示",
                    ma60_above,
                    f"{ma60_gap:+.1f}%",
                    "ETF收盘站上MA60",
                    "只作为提前量，不替代正式确认。",
                ),
                stage_item(
                    "连续站上年线",
                    ma250_confirmed,
                    f"{ma250_gap:+.1f}%",
                    "最近2个交易日均收于MA250上方",
                    "取消3%幅度要求，用连续收盘过滤单日假突破。",
                ),
                stage_item(
                    "ETF资金持续集中",
                    funding_confirmed,
                    (
                        f"{float(latest['amountRank']) * 100:.0f}%"
                        if pd.notna(latest["amountRank"])
                        else "—"
                    ),
                    "ETF成交额自身252日历史分位连续3日 ≥ 80%",
                    "港股指数成交额口径不可得，统一版使用ETF自身成交活跃度。",
                ),
                stage_item(
                    "拥挤风险",
                    crowding_hot,
                    (
                        f"{float(latest['amountRank']) * 100:.0f}%"
                        if pd.notna(latest["amountRank"])
                        else "—"
                    ),
                    "ETF成交额历史分位达到95%提示过热",
                    "只做风险提示，不参与启动确认。",
                ),
            ],
        },
        {
            "id": "leader",
            "number": "03",
            "title": "港股权重龙头确认",
            "subtitle": "前三严格确认，后七只只预警",
            "passed": leader_passed,
            "warning": leader_warning,
            "items": [
                stage_item(
                    "前三龙头强势事件",
                    strict_leader_confirmed,
                    f"{sum(event['strictQualified'] for event in leader_events)}次",
                    "权重前3近5个交易日单日涨幅≥5%，且达到自身120日收益95%分位",
                    "港股无统一涨停板，使用绝对涨幅与自身极端分位双重门槛。",
                ),
                stage_item(
                    "事件后持续",
                    strict_leader_confirmed,
                    "已确认" if strict_leader_confirmed else "待确认",
                    "次日继续上涨，且最新收盘不低于事件日收盘",
                    "停牌或数据未更新到专题截止日时不得确认。",
                ),
                stage_item(
                    "核心群体转强",
                    breadth_confirmed,
                    f"MA60 {above_ma60_count}/10 · 5日上涨 {positive_5d_count}/10",
                    "前十大至少5只站上MA60，且至少5只近5日上涨",
                    "龙头事件与群体广度必须同时通过。",
                ),
                stage_item(
                    "第4至10名异动",
                    secondary_alert,
                    f"{sum(event['qualified'] and event['rank'] > 3 for event in leader_events)}次",
                    "第4至10名近3日满足同一强势事件与持续性规则",
                    "只能触发预警，不能单独完成第三层。",
                ),
            ],
        },
    ]

    return {
        "meta": {
            "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "latestDate": as_of,
            "constituentDate": official_date,
            "dataStart": str(fund.iloc[0]["trade_date"]),
            "method": "港股QDII ETF价格代理 + 官方前十大成分股",
            "structureSource": "etf_price_proxy",
            "structureObjectName": "513970 ETF",
            "fundingObjectName": "513970 ETF",
            "heroDescription": (
                "长期位置、均线与资金活跃度看513970自身行情；"
                "市场共识直接看恒生消费官方前十大成分股。"
            ),
            "boundaryLabel": "统一生产监控 · ETF价格代理 · 港股专用口径",
            "chartFootnote": (
                "恒生消费指数历史日线当前未由Tushare返回，"
                "本图明确使用513970价格代理，不把ETF点位写成指数点位。"
            ),
            "sandbox": True,
            "productionIntegrated": True,
        },
        "target": {
            "slug": "513970-sh",
            "code": ETF_CODE,
            "name": "恒生消费ETF",
            "officialName": "景顺长城恒生消费交易型开放式指数证券投资基金(QDII)",
            "manager": "景顺长城基金",
            "indexCode": "HSCGSI.HI",
            "officialIndexCode": INDEX_CODE,
            "indexName": "恒生消费指数",
            "benchmarkCode": BENCHMARK_CODE,
            "benchmarkName": "恒生指数",
            "latestClose": as_float(latest["close"]),
            "latestPct": as_float(latest["pct_chg"]),
            "feederCode": None,
            "feederName": None,
        },
        "counterpart": {
            "href": "/hk-qdii/513230-sh",
            "code": "513230.SH / 017832.OF",
            "name": "华夏港股通消费",
        },
        "summary": {
            "label": label,
            "rhythmLabel": rhythm_label,
            "maLifecycle": ma_lifecycle,
            "conclusion": conclusion,
            "stagePassCount": stage_pass_count,
            "lowWarning": low_state["warning"],
            "belowMa250Days": below_ma250_days,
            "belowMa250TenDays": below_ma250_ten_days,
            "belowMa250FifteenDays": below_ma250_fifteen_days,
            "ma60Gap": as_float(ma60_gap),
            "ma250Gap": as_float(ma250_gap),
            "amountRankPct": (
                as_float(float(latest["amountRank"]) * 100)
                if pd.notna(latest["amountRank"])
                else None
            ),
            "fundingConfirmed": funding_confirmed,
            "strictLeaderConfirmed": strict_leader_confirmed,
            "breadthConfirmed": breadth_confirmed,
            "freshConstituentCount": breadth["freshCount"],
            "aboveMa60Count": above_ma60_count,
            "positive5dCount": positive_5d_count,
        },
        "stages": stages,
        "chart": [
            {
                "date": str(row["trade_date"]),
                "close": as_float(row["close"]),
                "ma20": as_float(row["ma20"]),
                "ma60": as_float(row["ma60"]),
                "ma250": as_float(row["ma250"]),
                "amountRankPct": (
                    as_float(float(row["amountRank"]) * 100)
                    if pd.notna(row["amountRank"])
                    else None
                ),
                "etfNormalized": as_float(row["etfNormalized"]),
                "benchmarkNormalized": as_float(row["benchmarkNormalized"]),
            }
            for _, row in chart.iterrows()
        ],
        "constituents": component_rows,
        "leaderEvents": leader_events,
        "notes": [
            "本页已纳入统一生产仪表盘、定时计算和发布流程，底层保留港股专用判断口径。",
            "恒生消费指数历史收盘与成交额未通过当前Tushare接口返回，因此低位、MA60、MA250和资金层使用513970 ETF行情作为代理。",
            "前十大名单及排序来自恒生指数有限公司公开接口；该接口只返回排序、不返回具体权重百分比。",
            "港股成分日线来自腾讯证券前复权行情；所有成分必须更新到专题截止日才可参与确认。",
            "港股无A股式统一涨停板，龙头事件使用单日涨幅≥5%且达到自身120日收益95%分位的双门槛。",
            "以上内容仅用于策略研究与观察，不构成投资建议。",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成513970恒生消费生产观察数据。")
    parser.add_argument(
        "--end-date",
        default=datetime.now().strftime("%Y%m%d"),
        help="数据截止日期，格式YYYYMMDD。",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="输出JSON路径。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    token = os.environ.get("TUSHARE_TOKEN")
    if not token:
        raise RuntimeError("缺少 TUSHARE_TOKEN。")
    import tushare as ts

    dashboard = build_dashboard(ts.pro_api(token), compact_date(args.end_date))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(dashboard, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"Generated {args.output} "
        f"as_of={dashboard['meta']['latestDate']} "
        f"label={dashboard['summary']['label']}"
    )


if __name__ == "__main__":
    main()

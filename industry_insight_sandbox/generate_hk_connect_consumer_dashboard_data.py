from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from generate_hk_qdii_dashboard_data import (
    CROWDING_HOT_PERCENTILE,
    FUNDING_CONFIRM_PERCENTILE,
    HISTORY_START,
    LOW_BELOW_MA250_PASS_DAYS,
    LOW_DEEP_10_PASS_DAYS,
    as_float,
    compact_date,
    evaluate_hk_breadth,
    evaluate_hk_leader_event,
    evaluate_low_position,
    evaluate_short_term_rhythm,
    fetch_tencent_daily,
    normalize_daily,
    return_over_period,
    rolling_percentile,
    stage_item,
)


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "data" / "hk_qdii" / "513230-sh.json"
ETF_CODE = "513230.SH"
FEEDER_CODE = "017832.OF"
INDEX_CODE = "931454.CSI"
BENCHMARK_CODE = "HSI"
TOP_COMPONENT_NAMES = {
    "09992.HK": ("泡泡玛特", "POP MART"),
    "09987.HK": ("百胜中国", "YUM CHINA"),
    "02020.HK": ("安踏体育", "ANTA SPORTS"),
    "09633.HK": ("农夫山泉", "NONGFU SPRING"),
    "00288.HK": ("万洲国际", "WH GROUP"),
    "06690.HK": ("海尔智家", "HAIER SMARTHOME"),
    "00300.HK": ("美的集团", "MIDEA GROUP"),
    "02319.HK": ("蒙牛乳业", "MENGNIU DAIRY"),
    "02331.HK": ("李宁", "LI NING"),
    "02313.HK": ("申洲国际", "SHENZHOU INTL"),
}


def fetch_latest_weights(pro: Any, requested_end_date: str) -> tuple[str, pd.DataFrame]:
    end = datetime.strptime(requested_end_date, "%Y%m%d")
    start = (end - timedelta(days=210)).strftime("%Y%m%d")
    weights = pro.index_weight(
        index_code=INDEX_CODE,
        start_date=start,
        end_date=requested_end_date,
    )
    if weights.empty:
        raise RuntimeError(f"{INDEX_CODE} 没有可用指数权重。")
    weights["trade_date"] = weights["trade_date"].astype(str)
    weights["weight"] = pd.to_numeric(weights["weight"], errors="coerce")
    weight_date = str(weights["trade_date"].max())
    snapshot = (
        weights[weights["trade_date"] == weight_date]
        .dropna(subset=["con_code", "weight"])
        .sort_values("weight", ascending=False)
        .reset_index(drop=True)
    )
    if len(snapshot) != 50:
        raise RuntimeError(f"{INDEX_CODE} 权重数量异常：{len(snapshot)}。")
    return weight_date, snapshot


def build_dashboard(pro: Any, requested_end_date: str) -> dict[str, Any]:
    index_daily = normalize_daily(
        pro.index_daily(
            ts_code=INDEX_CODE,
            start_date=HISTORY_START,
            end_date=requested_end_date,
            fields="ts_code,trade_date,open,high,low,close,pct_chg,amount",
        )
    )
    etf_daily = normalize_daily(
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
    feeder_nav = pro.fund_nav(
        ts_code=FEEDER_CODE,
        start_date=HISTORY_START,
        end_date=requested_end_date,
        fields="ts_code,nav_date,unit_nav,adj_nav",
    )
    weight_date, weights = fetch_latest_weights(pro, requested_end_date)

    if len(index_daily) < 370:
        raise RuntimeError(f"{INDEX_CODE} 日线不足：{len(index_daily)}。")
    if etf_daily.empty:
        raise RuntimeError(f"{ETF_CODE} 行情为空。")
    if benchmark.empty:
        raise RuntimeError("恒生指数基准行情为空。")
    as_of = min(
        str(index_daily.iloc[-1]["trade_date"]),
        str(etf_daily.iloc[-1]["trade_date"]),
        str(benchmark.iloc[-1]["trade_date"]),
    )
    index_daily = index_daily[index_daily["trade_date"] <= as_of].copy()
    etf_daily = etf_daily[etf_daily["trade_date"] <= as_of].copy()
    benchmark = benchmark[benchmark["trade_date"] <= as_of].copy()

    index_daily["amountRank"] = rolling_percentile(index_daily["amount"])
    last_120 = index_daily.dropna(subset=["ma250"]).tail(120)
    if len(last_120) != 120:
        raise RuntimeError("指数不足以计算完整的120日低位窗口。")
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

    latest = index_daily.iloc[-1]
    previous = index_daily.iloc[-2]
    latest_etf = etf_daily.iloc[-1]
    rhythm_label = evaluate_short_term_rhythm(index_daily)
    ma60_above = bool(latest["close"] > latest["ma60"])
    ma250_confirmed = bool(
        latest["close"] > latest["ma250"]
        and previous["close"] > previous["ma250"]
    )
    last_three_ranks = index_daily["amountRank"].tail(3)
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

    top_ten = weights.head(10).copy()
    component_frames: dict[str, pd.DataFrame] = {}
    for code in top_ten["con_code"]:
        quote_code = f"hk{str(code).split('.')[0]}"
        frame = normalize_daily(fetch_tencent_daily(quote_code))
        frame = frame[frame["trade_date"] <= as_of].copy()
        if len(frame) < 250:
            raise RuntimeError(f"{code} 日线不足：{len(frame)}。")
        component_frames[str(code)] = frame

    market_trade_dates = [
        str(value) for value in index_daily["trade_date"].tail(10)
    ]
    component_rows = []
    leader_events = []
    for rank, (_, weight_row) in enumerate(top_ten.iterrows(), start=1):
        code = str(weight_row["con_code"])
        name, english_name = TOP_COMPONENT_NAMES.get(code, (code, code))
        frame = component_frames[code].copy()
        frame["volumeRatio20"] = frame["volume"] / frame["volume"].rolling(20).mean()
        row = frame.iloc[-1]
        component_rows.append(
            {
                "code": code,
                "name": name,
                "englishName": english_name,
                "rank": rank,
                "weight": as_float(weight_row["weight"]),
                "latestDate": str(row["trade_date"]),
                "dataFresh": str(row["trade_date"]) == as_of,
                "latestClose": as_float(row["close"]),
                "pct1d": as_float(row["pct_chg"]),
                "ret5d": return_over_period(frame, 5),
                "ret20d": return_over_period(frame, 20),
                "aboveMa60": bool(row["close"] > row["ma60"]),
                "aboveMa250": bool(row["close"] > row["ma250"]),
                "volumeRatio20": as_float(row["volumeRatio20"]),
            }
        )
        event = evaluate_hk_leader_event(
            code=code,
            name=name,
            rank=rank,
            as_of=as_of,
            daily=frame,
            market_trade_dates=market_trade_dates,
        )
        if event:
            leader_events.append(event)

    breadth = evaluate_hk_breadth(component_rows)
    strict_leader_confirmed = any(
        event["strictQualified"] for event in leader_events
    )
    secondary_alert = any(
        event["qualified"] and event["rank"] > 3 for event in leader_events
    )
    leader_passed = strict_leader_confirmed and breadth["confirmed"]
    leader_warning = not leader_passed and (
        strict_leader_confirmed or secondary_alert or breadth["confirmed"]
    )

    stage_pass_count = sum(
        [low_state["passed"], breakout_passed, leader_passed]
    )
    if stage_pass_count == 3:
        label = "启动确认"
        conclusion = "低位、指数量价与权重龙头三层条件已经闭环。"
    elif low_state["passed"] and breakout_passed and leader_warning:
        label = "接近启动"
        conclusion = "低位与指数量价条件已完成，等待前三权重龙头严格确认。"
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
            clues.append("指数站上MA60")
        if funding_confirmed:
            clues.append("指数成交分位达标")
        if leader_warning:
            clues.append("权重成分出现转强线索")
        conclusion = f"当前线索：{'、'.join(clues) or '尚未形成明确闭环'}。"
    else:
        label = "未启动"
        conclusion = "指数低位、量价与权重龙头尚未形成可验证的启动链路。"

    chart = index_daily.tail(400)[
        ["trade_date", "close", "ma20", "ma60", "ma250", "amountRank"]
    ].merge(
        benchmark[["trade_date", "close"]].rename(
            columns={"close": "benchmarkClose"}
        ),
        on="trade_date",
        how="left",
    )
    first_index = float(chart.iloc[0]["close"])
    first_benchmark = chart["benchmarkClose"].dropna().iloc[0]
    chart["etfNormalized"] = chart["close"] / first_index * 100
    chart["benchmarkNormalized"] = (
        chart["benchmarkClose"] / first_benchmark * 100
    )

    ma60_gap = (latest["close"] / latest["ma60"] - 1) * 100
    ma250_gap = (latest["close"] / latest["ma250"] - 1) * 100
    amount_rank_pct = (
        as_float(float(latest["amountRank"]) * 100)
        if pd.notna(latest["amountRank"])
        else None
    )
    feeder_latest = None
    feeder_latest_date = None
    if not feeder_nav.empty:
        feeder_nav = feeder_nav.copy()
        feeder_nav["nav_date"] = feeder_nav["nav_date"].astype(str)
        feeder_nav = feeder_nav.sort_values("nav_date")
        feeder_row = feeder_nav.iloc[-1]
        feeder_latest = as_float(feeder_row["unit_nav"])
        feeder_latest_date = str(feeder_row["nav_date"])

    stages = [
        {
            "id": "structure",
            "number": "01",
            "title": "低位收敛",
            "subtitle": "直接使用931454.CSI指数点位",
            **low_state,
            "items": [
                stage_item(
                    "年线下停留",
                    below_ma250_days >= LOW_BELOW_MA250_PASS_DAYS,
                    f"{below_ma250_days}/120日",
                    "过去120日中，指数收盘低于MA250的天数 ≥ 60",
                    "达到40日先预警；本页不使用ETF价格代理。",
                ),
                stage_item(
                    "加速下跌记录",
                    below_ma250_ten_days >= LOW_DEEP_10_PASS_DAYS,
                    f"{below_ma250_ten_days}/120日",
                    "过去120日中，指数收盘低于MA250至少10%的天数 ≥ 24",
                    "达到12日先预警；两条低位路径满足其一即可。",
                ),
                stage_item(
                    "深度低位记录",
                    False,
                    f"{below_ma250_fifteen_days}/120日",
                    "展示指数低于MA250至少15%的天数，不作为硬条件",
                    "用于描述低位深度。",
                ),
            ],
        },
        {
            "id": "breakout",
            "number": "02",
            "title": "量价趋势确认",
            "subtitle": "指数MA60预警，MA250与成交分位确认",
            "passed": breakout_passed,
            "warning": breakout_warning,
            "items": [
                stage_item(
                    "MA60提前提示",
                    ma60_above,
                    f"{ma60_gap:+.1f}%",
                    "931454.CSI指数收盘站上MA60",
                    "只作为提前量，不替代正式确认。",
                ),
                stage_item(
                    "连续站上年线",
                    ma250_confirmed,
                    f"{ma250_gap:+.1f}%",
                    "最近2个交易日指数均收于MA250上方",
                    "用连续收盘过滤单日假突破。",
                ),
                stage_item(
                    "指数成交持续集中",
                    funding_confirmed,
                    f"{amount_rank_pct:.0f}%" if amount_rank_pct is not None else "—",
                    "指数成交额自身252日历史分位连续3日 ≥ 80%",
                    "直接使用931454.CSI成交额，不使用513230成交额代理。",
                ),
                stage_item(
                    "拥挤风险",
                    crowding_hot,
                    f"{amount_rank_pct:.0f}%" if amount_rank_pct is not None else "—",
                    "指数成交额历史分位达到95%提示过热",
                    "只做风险提示，不参与启动确认。",
                ),
            ],
        },
        {
            "id": "leader",
            "number": "03",
            "title": "港股权重龙头确认",
            "subtitle": "正式月度权重前三严格确认",
            "passed": leader_passed,
            "warning": leader_warning,
            "items": [
                stage_item(
                    "前三龙头强势事件",
                    strict_leader_confirmed,
                    f"{sum(event['strictQualified'] for event in leader_events)}次",
                    "权重前3近5个交易日单日涨幅≥5%，且达到自身120日收益95%分位",
                    "前三按中证指数月度权重排序。",
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
                    breadth["confirmed"],
                    (
                        f"MA60 {breadth['aboveMa60Count']}/10 · "
                        f"5日上涨 {breadth['positive5dCount']}/10"
                    ),
                    "前十大全部新鲜，至少5只站上MA60且至少5只近5日上涨",
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
            "constituentDate": weight_date,
            "dataStart": str(index_daily.iloc[0]["trade_date"]),
            "method": "中证港股通消费主题指数 + 正式月度权重前十大",
            "structureSource": "tracking_index",
            "structureObjectName": "港股通消费指数",
            "fundingObjectName": "港股通消费指数",
            "heroDescription": (
                "017832是场外联接基金，策略判断下沉到底层ETF 513230及其真实"
                "跟踪指数931454.CSI；长期位置、成交活跃度和权重龙头均使用指数直接数据。"
            ),
            "boundaryLabel": "统一生产监控 · 指数直接版 · 港股专用口径",
            "chartFootnote": (
                "本图直接使用931454.CSI指数点位、MA60、MA250及指数成交额历史分位。"
            ),
            "sandbox": True,
            "productionIntegrated": True,
        },
        "target": {
            "slug": "513230-sh",
            "code": ETF_CODE,
            "name": "港股通消费ETF",
            "officialName": "华夏中证港股通消费主题交易型开放式指数证券投资基金",
            "manager": "华夏基金",
            "indexCode": INDEX_CODE,
            "officialIndexCode": INDEX_CODE,
            "indexName": "中证港股通消费主题指数",
            "benchmarkCode": BENCHMARK_CODE,
            "benchmarkName": "恒生指数",
            "latestClose": as_float(latest_etf["close"]),
            "latestPct": as_float(latest_etf["pct_chg"]),
            "feederCode": FEEDER_CODE,
            "feederName": "华夏中证港股通消费主题ETF发起式联接A",
            "feederLatestNav": feeder_latest,
            "feederLatestDate": feeder_latest_date,
        },
        "counterpart": {
            "href": "/hk-qdii/513970-sh",
            "code": "513970.SH",
            "name": "景顺长城恒生消费",
        },
        "summary": {
            "label": label,
            "rhythmLabel": rhythm_label,
            "conclusion": conclusion,
            "stagePassCount": stage_pass_count,
            "lowWarning": low_state["warning"],
            "belowMa250Days": below_ma250_days,
            "belowMa250TenDays": below_ma250_ten_days,
            "belowMa250FifteenDays": below_ma250_fifteen_days,
            "ma60Gap": as_float(ma60_gap),
            "ma250Gap": as_float(ma250_gap),
            "amountRankPct": amount_rank_pct,
            "fundingConfirmed": funding_confirmed,
            "strictLeaderConfirmed": strict_leader_confirmed,
            "breadthConfirmed": breadth["confirmed"],
            "freshConstituentCount": breadth["freshCount"],
            "aboveMa60Count": breadth["aboveMa60Count"],
            "positive5dCount": breadth["positive5dCount"],
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
            "017832是场外ETF联接A类，行业启动判断使用其底层ETF 513230和真实跟踪指数931454.CSI。",
            "指数日线、成交额及50只月度权重均来自Tushare；页面展示正式权重前十大。",
            "港股成分日线来自腾讯证券前复权行情；所有前十大必须更新到专题截止日才可完成群体确认。",
            "本页与513970属于同一港股消费集群，但指数权重和龙头排序分别计算。",
            "以上内容仅用于策略研究与观察，不构成投资建议。",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成513230/017832港股通消费观察数据。")
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

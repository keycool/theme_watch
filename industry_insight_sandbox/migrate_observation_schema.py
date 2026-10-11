#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
把已生成的观察 JSON 迁移到「客观描述」schema（纯派生，不联网）。

背景：观察层不再输出方向性判断。生产侧由 generate_dashboard_data.py 直接产出新结构；
本脚本用于把**已存在**的 JSON 就地补齐 / 清洗，使页面在下一轮正式生成之前也能一致渲染。

做什么
------
1. 删除判断字段：summary.label / summary.rhythmLabel / summary.conclusion
              maLifecycle.label / maLifecycle.capitalInterface / maLifecycle.safetyMarginPassed
              summary.strictLeaderConfirmed / lowWarning / ma60Watch / ma60Near
              / fundingConfirmed / crowdingHot / crowdingOverheated
              / topTenLimitAlert / secondaryLimitAlert
2. 重命名 maLifecycle 字段为中性几何名（initialStartDate → ma60CrossUpDate 等）
3. 从 JSON 内嵌的 chart（320 根 K 线）派生 summary.observation（位置/时间/广度/强度 + 分位）
4. 对 hk_qdii 与 overview 同样处理

不做什么
--------
- 不重算任何策略判定；不改 chart / weights / components 原始数据。
- 不写 live-data（那是上游同步产物）。
"""

from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"

LIFECYCLE_RENAME = {
    "initialStartDate": "ma60CrossUpDate",
    "trendConfirmedDate": "firstAboveMa250Date",
    "warmUpDate": "ma20CrossUpDate",
    "deathCrossDate": "ma60BelowMa250Date",
    "initialStartToday": "ma60CrossUpToday",
    "trendConfirmedToday": "aboveMa250Today",
    "initialStartActive": "stateAboveMa60",
    "trendConfirmedActive": "stateAboveMa250",
    "initialStartInvalidated": "ma60CrossUpInvalidated",
}

LIFECYCLE_DROP = {"label", "capitalInterface", "safetyMarginPassed"}

SUMMARY_DROP = {
    "label",
    "rhythmLabel",
    "conclusion",
    "strictLeaderConfirmed",
    "lowWarning",
    "ma60Watch",
    "ma60Near",
    "fundingConfirmed",
    "crowdingHot",
    "crowdingOverheated",
    "topTenLimitAlert",
    "secondaryLimitAlert",
}

SUMMARY_RENAME = {"ma60BreakoutToday": "ma60CrossUpToday"}

OVERVIEW_DROP = {
    "label",
    "rhythmLabel",
    "maLifecycleLabel",
    "maSafetyMarginPassed",
    "capitalInterface",
    "conclusion",
    "lowWarning",
    "ma60Watch",
    "ma60Near",
    "fundingConfirmed",
    "crowdingHot",
    "topTenLimitAlert",
    "secondaryLimitAlert",
}

OVERVIEW_RENAME = {
    "initialStartToday": "ma60CrossUpToday",
    "trendConfirmedToday": "aboveMa250Today",
    "ma60BreakoutToday": "ma60CrossUpToday",
}

CONVERGED_MIN_DAYS = 20

# stateCode 是纯几何：只由最新收盘价与三条均线比较得出，
# 不再由旧的 label（未形成 / 初始启动 …）映射而来——那个映射带着事件门控，
# 会让「站在全部均线之上」的标的被标成 below_ma20（2026-09-19 修正）。


def _num(value):
    try:
        if value is None:
            return None
        f = float(value)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def rank_pct(values: list[float], current: float | None) -> float | None:
    if current is None:
        return None
    clean = [v for v in values if v is not None]
    if len(clean) < 60:
        return None
    return round(sum(1 for v in clean if v <= current) / len(clean) * 100, 2)


def consecutive_tail(flags: list[bool]) -> int:
    count = 0
    for flag in reversed(flags):
        if not flag:
            break
        count += 1
    return count


def build_observation(chart: list[dict], summary: dict, lifecycle: dict) -> dict:
    closes = [_num(row.get("close")) for row in chart]
    ma20s = [_num(row.get("ma20")) for row in chart]
    ma60s = [_num(row.get("ma60")) for row in chart]
    ma250s = [_num(row.get("ma250")) for row in chart]
    amounts = [_num(row.get("amountRatio20")) for row in chart]

    def gap(series):
        out = []
        for close, ma in zip(closes, series):
            out.append(None if (close is None or ma in (None, 0)) else (close / ma - 1) * 100)
        return out

    gap20, gap60, gap250 = gap(ma20s), gap(ma60s), gap(ma250s)
    latest_close = closes[-1] if closes and closes[-1] is not None else None
    window_high = max([c for c in closes if c is not None], default=None)

    def last(series):
        return series[-1] if series else None

    above60 = [c is not None and m is not None and c >= m for c, m in zip(closes, ma60s)]
    above250 = [c is not None and m is not None and c >= m for c, m in zip(closes, ma250s)]
    below60 = [c is not None and m is not None and c < m for c, m in zip(closes, ma60s)]

    active = summary.get("activeCount") or 0
    ma60_count = summary.get("aboveMa60Count")
    ma250_count = summary.get("aboveMa250Count")
    # 广度分母 = 成分股样本数。A 股主题用 coreCount，港股 QDII 没有 coreCount，
    # 用 freshConstituentCount（成分股 10 只）。缺样本就整列留空，不补 0。
    breadth_base = summary.get("coreCount") or summary.get("freshConstituentCount") or 0

    return {
        "position": {
            "maStackCode": lifecycle.get("maStackCode"),
            "ma20GapPct": last(gap20),
            "ma60GapPct": last(gap60),
            "ma250GapPct": last(gap250),
            "ma60GapRankPct": rank_pct(gap60, last(gap60)),
            "ma250GapRankPct": rank_pct(gap250, last(gap250)),
            "closeRankPct": rank_pct(closes, latest_close),
            "drawdownFromWindowHighPct": (
                round((latest_close / window_high - 1) * 100, 4)
                if (latest_close is not None and window_high) else None
            ),
            "windowDays": len(chart),
        },
        "duration": {
            "aboveMa60Days": consecutive_tail(above60),
            "aboveMa250Days": consecutive_tail(above250),
            "belowMa60Days": consecutive_tail(below60),
            "ma60CrossUpDate": lifecycle.get("ma60CrossUpDate"),
            "firstAboveMa250Date": lifecycle.get("firstAboveMa250Date"),
            "ma60CrossUpDaysAgo": None,
        },
        "breadth": {
            "coreCount": breadth_base,
            "coreCoveragePct": _num(summary.get("coreCoverage")),
            "activeCount": active,
            "aboveMa60Count": ma60_count,
            "aboveMa250Count": ma250_count,
            "aboveMa60Pct": (
                round(ma60_count / breadth_base * 100, 2)
                if (ma60_count is not None and breadth_base)
                else None
            ),
            "aboveMa250Pct": (
                round(ma250_count / breadth_base * 100, 2)
                if (ma250_count is not None and breadth_base)
                else None
            ),
        },
        "strength": {
            "amountRatio20": _num(summary.get("amountRatio20")),
            "amountRatio20RankPct": rank_pct(amounts, _num(summary.get("amountRatio20"))),
            "absorptionRankPct": _num(summary.get("absorptionRankPct")),
            "etfAmountRankPct": _num(summary.get("etfAmountRankPct")),
            "relativeExcess120Pct": _num(summary.get("relativeExcess120")),
        },
    }


def above_flags(chart: list[dict]) -> dict[str, bool]:
    """最新一根收盘价相对三条均线的位置（纯几何，可一行复算）。"""
    row = chart[-1] if chart else {}
    close = _num(row.get("close"))
    out = {}
    for key in ("ma20", "ma60", "ma250"):
        ma = _num(row.get(key))
        out[key] = bool(close is not None and ma is not None and close >= ma)
    return out


def geometry_state_code(chart: list[dict], convergence_days: int | None) -> str:
    flags = above_flags(chart)
    if flags.get("ma250"):
        return "above_ma250"
    if flags.get("ma60"):
        return "above_ma60"
    if flags.get("ma20"):
        return "above_ma20"
    if (convergence_days or 0) >= CONVERGED_MIN_DAYS:
        return "below_ma20_converged"
    return "below_ma20"


def ma_stack_code(chart: list[dict]) -> str:
    row = chart[-1] if chart else {}
    values = []
    for key, name in (("ma20", "MA20"), ("ma60", "MA60"), ("ma250", "MA250")):
        value = _num(row.get(key))
        if value is not None:
            values.append((name, value))
    if not values:
        return "MA--"
    ordered = sorted(values, key=lambda item: item[1], reverse=True)
    return ">".join(name for name, _ in ordered)


TEXT_REPLACEMENTS = [
    ("主启动标签", "读数"),
    ("启动标签", "读数"),
    ("启动确认", "条件读数"),
    ("初始启动", "MA60 上穿"),
    ("年线趋势确认", "站上 MA250"),
    ("突破年线", "站上 MA250"),
    ("站上年线", "站上 MA250"),
    ("年线下", "MA250 下方"),
    ("深度低位", "低于 MA250 10%"),
    ("有效低位", "低于 MA250 5%"),
    ("低位收敛", "价格位置"),
    ("低位条件", "位置条件"),
    ("低位结构", "位置结构"),
    ("低位停留", "MA250 下方停留"),
    ("MA250确认", "MA250 读数"),
    ("资金确认", "资金读数"),
    ("龙头确认", "龙头读数"),
    ("完成闭环", "三项同时满足"),
    ("闭环", "三项同时满足"),
    ("提前提示", "位置提示"),
    ("观察窗口", "区间"),
    ("观察中", "区间内"),
    ("可通过", "达到"),
    ("预警", "刻度"),
    ("过热", "拥挤"),
    ("转强", "上行"),
    ("确认", "读数"),
    # —— 第二轮：数据里仍出现的具体措辞（2026-09-19 复核）——
    ("MA60观察窗", "MA60 区间"),
    ("观察窗", "区间"),
    ("观察对象明确", "样本口径明确"),
    ("直接观察指数前10大权重股", "以指数前10大权重股为样本"),
    ("深跌10%", "低于MA250 10%"),
    ("待确认", "未达"),
    ("未确认", "未达"),
    ("通过要求分别达到", "达到门槛分别要求"),
    ("通过门槛", "门槛"),
    ("必须同时通过", "必须同时满足"),
    ("两条低位路径", "两条位置路径"),
    ("用于描述低位深度", "用于描述低于MA250 的幅度"),
    ("低位、MA60", "低于MA250 的幅度、MA60"),
    ("策略研究与观察", "策略研究与方法验证"),
    ("行业启动判断", "行业读数"),
    ("观察", "读数"),
    # —— 第三轮：把已生成数据里的阶段/条目标题对齐到生成器当前口径 ——
    ("带量站上 MA250", "均线与成交额"),
    ("权重龙头读数", "核心成分股"),
    ("低于 MA250 5%停留", "低于MA250 5% 的天数"),
    ("加速下跌记录", "单日跌幅记录"),
    ("低于 MA250 10%记录", "低于MA250 10% 的天数"),
    ("MA60区间", "距MA60 区间"),
    ("资金持续集中", "成交额分位持续"),
    ("拥挤风险", "拥挤度分位"),
    ("样本口径明确", "成分样本数"),
    ("次级龙头异动", "第4至10名异动记录"),
    ("前三龙头涨停", "前三名涨停记录"),
    ("涨停后持续", "涨停后连续性"),
    ("核心群体上行", "核心成分 MA60 广度"),
]


def neutralize_text(value: str | None) -> str | None:
    if not value:
        return value
    result = value
    for old, new in TEXT_REPLACEMENTS:
        result = result.replace(old, new)
    return result


def migrate_stages(topic: dict) -> None:
    """阶段卡的标题 / 规则 / 注释也一并中性化（生产侧已在生成器里改，
    这里是给已生成的数据补做）。"""
    for stage in topic.get("stages") or []:
        if isinstance(stage.get("title"), str):
            stage["title"] = neutralize_text(stage["title"])
        if isinstance(stage.get("subtitle"), str):
            stage["subtitle"] = neutralize_text(stage["subtitle"])
        for item in stage.get("items") or []:
            for key in ("title", "rule", "note", "value", "subtitle"):
                if isinstance(item.get(key), str):
                    item[key] = neutralize_text(item[key])
    if isinstance(topic.get("notes"), list):
        topic["notes"] = [neutralize_text(n) for n in topic["notes"] if isinstance(n, str)]


def migrate_topic(topic: dict) -> dict:
    summary = topic.get("summary") or {}
    lifecycle = summary.get("maLifecycle") or {}

    lifecycle = {k: v for k, v in lifecycle.items() if k not in LIFECYCLE_DROP}
    for old, new in LIFECYCLE_RENAME.items():
        if old in lifecycle:
            lifecycle[new] = lifecycle.pop(old)
    chart = topic.get("chart") or []
    # 几何三件套一律按最新一根 K 线重算，不沿用旧值：
    # 旧值来自带事件门控的 label，和图上数字对不上。
    flags = above_flags(chart)
    lifecycle["aboveMa20"] = flags["ma20"]
    lifecycle["aboveMa60"] = flags["ma60"]
    lifecycle["aboveMa250"] = flags["ma250"]
    lifecycle["maStackCode"] = ma_stack_code(chart)
    lifecycle["stateCode"] = geometry_state_code(
        chart, _num(lifecycle.get("convergenceDays"))
    )
    summary["maLifecycle"] = lifecycle

    for old, new in SUMMARY_RENAME.items():
        if old in summary:
            summary[new] = summary.pop(old)
    for key in list(summary):
        if key in SUMMARY_DROP:
            summary.pop(key)

    summary["observation"] = build_observation(chart, summary, lifecycle)
    topic["summary"] = summary

    migrate_stages(topic)
    return topic


def migrate_overview(overview: dict) -> dict:
    for item in overview.get("targets") or []:
        # 迁移过程中曾补写过一个嵌套 summary（全空值、无任何消费方），清掉，
        # 只保留顶层的 maStackCode / maStateCode / observation。
        item.pop("summary", None)
        for key in list(item):
            if key in OVERVIEW_DROP:
                item.pop(key)
        for old, new in OVERVIEW_RENAME.items():
            if old in item:
                item[new] = item.pop(old)
        for stage in item.get("stageStates") or []:
            if isinstance(stage.get("title"), str):
                stage["title"] = neutralize_text(stage["title"])
        lifecycle = item.get("maLifecycle") or {}
        if not lifecycle and item.get("maStackCode"):
            item.setdefault("maStateCode", item.get("maStateCode"))
    return overview


def main() -> None:
    targets: list[Path] = []
    targets.extend(sorted((DATA_DIR / "topics").glob("*.json")))
    targets.extend(sorted((DATA_DIR / "hk_qdii").glob("*.json")))

    changed = 0
    by_slug: dict[str, dict] = {}
    for path in targets:
        try:
            topic = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[skip] {path.name}: {exc}")
            continue
        before = json.dumps(topic, ensure_ascii=False, sort_keys=True)
        migrate_topic(topic)
        after = json.dumps(topic, ensure_ascii=False, sort_keys=True)
        if before != after:
            path.write_text(json.dumps(topic, ensure_ascii=False, indent=2), encoding="utf-8")
            changed += 1
        slug = (topic.get("target") or {}).get("slug")
        if slug:
            by_slug[slug] = topic
    print(f"[topics/hk_qdii] 迁移 {changed}/{len(targets)} 个文件")

    # all_topics.json 里的条目自带 chart，可直接派生
    all_topics_path = DATA_DIR / "all_topics.json"
    if all_topics_path.exists():
        payload = json.loads(all_topics_path.read_text(encoding="utf-8"))
        items = payload if isinstance(payload, list) else (payload.get("targets") or [])
        for topic in items:
            migrate_topic(topic)
            slug = (topic.get("target") or {}).get("slug")
            if slug:
                by_slug.setdefault(slug, topic)
        all_topics_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("[write] all_topics.json")

    # overview 行没有 chart，按 slug 从主题文件带过来
    overview_path = DATA_DIR / "overview.json"
    if overview_path.exists():
        payload = json.loads(overview_path.read_text(encoding="utf-8"))
        migrate_overview(payload)
        carried = 0
        for item in payload.get("targets") or []:
            slug = item.get("slug")
            source = by_slug.get(slug)
            if not source:
                continue
            src_summary = source.get("summary") or {}
            src_lifecycle = src_summary.get("maLifecycle") or {}
            item["maStackCode"] = src_lifecycle.get("maStackCode")
            item["maStateCode"] = src_lifecycle.get("stateCode")
            item["observation"] = src_summary.get("observation")
            carried += 1
        overview_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[write] overview.json（补齐 {carried} 行）")


if __name__ == "__main__":
    main()

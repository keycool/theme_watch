from __future__ import annotations

"""构建「全市场一起跌 vs 单独被砸」的横截面读数，并回填到观察层。

来源：2026-09-18 急跌假设历史验证里**唯一显著**的结论——
    「急跌 + 全市场一起跌」−「急跌 + 单独被砸」= +1.50%（20 日超额，CI[+0.51%, +2.41%] 不含 0）
    （该验证已归档：D:/CC/Industry Insight/急跌假设-历史验证结果-v0.1.md）

定义（忠实于验证口径，不使用被证否的「同日触发数 ≥5」，那个误标率 68.3%）：
    marketRet5MedianPct <= -3%  -> 全市场一起跌
    本标的 ret5 <= -3% 且横截面没跌 -> 单独被砸

⚠️ 这是**纯观察读数**，不含任何买卖含义；也不构成对后续走势的判断。
⚠️ 历史数据无法补：存量 JSON 没有历史横截面，该读数只能从首次运行日起逐日积累，
   因此每个 context 都带 contextAsOf，避免被误读成「历史上一直有」。

用法（必须在 generate 与 merge 之后运行，此时 overview 已含全部 23 个标的）：
    python build_market_context.py
"""

import argparse
import json
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
ALL_TOPICS_PATH = DATA_DIR / "all_topics.json"
HK_TARGETS_PATH = ROOT / "hk_qdii_targets.json"
OVERVIEW_PATH = DATA_DIR / "overview.json"
TOPICS_DIR = DATA_DIR / "topics"
OUTPUT_PATH = DATA_DIR / "market_context.json"

SCHEMA_VERSION = "1.0"
DECLINE_THRESHOLD_PCT = -3.0
RET5_WINDOW = 5  # 5 个交易日收益 -> 需要 6 个收盘价

REGIME_MARKET_WIDE = "market_wide"
REGIME_SINGLE_NAME = "single_name"
REGIME_NONE = "none"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def ret5_pct(chart: list[dict[str, Any]]) -> float | None:
    """最近 5 个交易日的收益（百分数）。样本不足返回 None。"""
    closes = [
        float(row["close"])
        for row in chart
        if isinstance(row.get("close"), (int, float))
    ]
    if len(closes) < RET5_WINDOW + 1:
        return None
    first = closes[-(RET5_WINDOW + 1)]
    if first == 0:
        return None
    return (closes[-1] / first - 1) * 100


def classify(own: float | None, market_median: float | None) -> str:
    if own is None or market_median is None:
        return REGIME_NONE
    if own > DECLINE_THRESHOLD_PCT:
        return REGIME_NONE
    if market_median <= DECLINE_THRESHOLD_PCT:
        return REGIME_MARKET_WIDE
    return REGIME_SINGLE_NAME


def collect_topics() -> tuple[list[dict[str, Any]], dict[str, Path], int]:
    """返回（全部 topic、code -> 磁盘路径、core topic 数量）。"""
    topics: list[dict[str, Any]] = []
    paths: dict[str, Path] = {}

    core = read_json(ALL_TOPICS_PATH)
    for topic in core:
        code = str(topic["target"]["code"])
        topics.append(topic)
        slug = topic["target"].get("slug") or code.lower().replace(".", "-")
        paths[code] = TOPICS_DIR / f"{slug}.json"

    for config in read_json(HK_TARGETS_PATH):
        path = ROOT / config["dataFile"]
        topic = read_json(path)
        code = str(topic["target"]["code"])
        topics.append(topic)
        paths[code] = path

    return topics, paths, len(core)


def build_context(topics: list[dict[str, Any]], as_of: str) -> dict[str, dict[str, Any]]:
    own: dict[str, float | None] = {}
    for topic in topics:
        code = str(topic["target"]["code"])
        own[code] = ret5_pct(topic.get("chart", []))

    values = [value for value in own.values() if value is not None]
    market_median = median(values) if values else None

    contexts: dict[str, dict[str, Any]] = {}
    for code, value in own.items():
        contexts[code] = {
            "marketRet5MedianPct": (
                None if market_median is None else round(market_median, 4)
            ),
            "ownRet5Pct": None if value is None else round(value, 4),
            "declineRegime": classify(value, market_median),
            "declineThresholdPct": DECLINE_THRESHOLD_PCT,
            "sampleCount": len(values),
            "contextAsOf": as_of,
        }
    return contexts


def attach(topic: dict[str, Any], context: dict[str, Any]) -> bool:
    """把 context 挂到 topic 的 observation 上；返回是否发生变化。"""
    summary = topic.setdefault("summary", {})
    observation = summary.get("observation")
    if not isinstance(observation, dict):
        return False
    if observation.get("context") == context:
        return False
    observation["context"] = context
    return True


def build_and_backfill(
    overview_path: Path = OVERVIEW_PATH,
    output_path: Path = OUTPUT_PATH,
) -> dict[str, Any]:
    """计算横截面读数并回填全部产物；返回结果摘要。

    这是给编排脚本（`run_etf_constituent_workflow.py`）预留的**库接口**：
    既可以直接 import 调用，也可以用 `python build_market_context.py` 跑。
    调用前提：generate 与 merge 都已完成（overview 里必须有全部 23 个标的）。
    """
    topics, paths, core_count = collect_topics()
    overview = read_json(overview_path)
    dates = {str(row.get("latestDate")) for row in overview.get("targets", [])}
    if len(dates) != 1:
        raise RuntimeError(f"Overview latestDate is not unique: {sorted(dates)}")
    as_of = str(next(iter(dates)))

    contexts = build_context(topics, as_of)

    # 1) 回填单标的产物（all_topics 与各 topic / hk_qdii 文件）
    changed = 0
    for topic in topics:
        code = str(topic["target"]["code"])
        if attach(topic, contexts[code]):
            changed += 1
    write_json(ALL_TOPICS_PATH, topics[:core_count])
    del core_count  # 仅用于切出 core 段，勿在后续误用
    for code, path in paths.items():
        if not path.exists():
            continue
        single = read_json(path)
        if attach(single, contexts[code]):
            write_json(path, single)
            changed += 1

    # 2) 回填 overview
    for row in overview["targets"]:
        code = str(row.get("code"))
        context = contexts.get(code)
        if context is None:
            continue
        observation = row.get("observation")
        if isinstance(observation, dict) and observation.get("context") != context:
            observation["context"] = context
            changed += 1
    write_json(overview_path, overview)

    # 3) 市场级读数存档
    regimes: dict[str, int] = {}
    for context in contexts.values():
        regimes[context["declineRegime"]] = regimes.get(context["declineRegime"], 0) + 1
    market_median = next(iter(contexts.values()))["marketRet5MedianPct"]
    payload: dict[str, Any] = {
        "meta": {
            "schemaVersion": SCHEMA_VERSION,
            "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "asOf": as_of,
            "sampleCount": next(iter(contexts.values()))["sampleCount"],
            "marketRet5MedianPct": market_median,
            "declineThresholdPct": DECLINE_THRESHOLD_PCT,
            "decisionUse": False,
            "note": (
                "纯观察读数：区分「全市场一起跌」与「单独被砸」，"
                "来源于 2026-09-18 急跌验证中唯一显著的结论；不含买卖含义。"
                "历史横截面无法补算，仅从首次运行日起积累。"
            ),
        },
        "regimeCounts": regimes,
        "targets": contexts,
        "backfillCount": changed,
    }
    write_json(output_path, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="构建并回填横截面读数。")
    parser.add_argument("--overview", type=Path, default=OVERVIEW_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()

    payload = build_and_backfill(args.overview, args.output)
    print(
        f"market_context asOf={payload['meta']['asOf']} "
        f"median={payload['meta']['marketRet5MedianPct']} "
        f"regimes={payload['regimeCounts']} "
        f"backfilled={payload['backfillCount']}"
    )


if __name__ == "__main__":
    main()

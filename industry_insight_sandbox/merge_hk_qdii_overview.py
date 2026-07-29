from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_OVERVIEW = ROOT / "data" / "overview.json"
DEFAULT_TARGETS = ROOT / "hk_qdii_targets.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build_overview_row(config: dict[str, Any], dashboard: dict[str, Any]) -> dict[str, Any]:
    meta = dashboard["meta"]
    target = dashboard["target"]
    summary = dashboard["summary"]
    stages = dashboard["stages"]
    if meta.get("productionIntegrated") is not True:
        raise RuntimeError(f"{target['code']} is not marked as production integrated.")
    return {
        "slug": target["slug"],
        "bucket": config["bucket"],
        "order": config["order"],
        "code": target["code"],
        "name": target["name"],
        "kind": config["kind"],
        "route": config["route"],
        "indexCode": target["indexCode"],
        "indexName": target["indexName"],
        "label": summary["label"],
        "latestDate": meta["latestDate"],
        "weightDate": meta["constituentDate"],
        "latestClose": target["latestClose"],
        "latestPct": target["latestPct"],
        "ma250Gap": summary["ma250Gap"],
        "absorptionRankPct": summary["amountRankPct"],
        "fundingConfirmed": summary["fundingConfirmed"],
        "crowdingHot": bool(
            summary["amountRankPct"] is not None
            and summary["amountRankPct"] >= 95
        ),
        "belowMa250Days": summary["belowMa250Days"],
        "belowMa250TenDays": summary["belowMa250TenDays"],
        "stagePassCount": summary["stagePassCount"],
        "stageStates": [
            {
                "id": stage["id"],
                "title": stage["title"],
                "passed": stage["passed"],
                "warning": stage["warning"],
            }
            for stage in stages
        ],
    }


def merge_overview(
    overview: dict[str, Any],
    configs: list[dict[str, Any]],
    dashboards: list[dict[str, Any]],
) -> dict[str, Any]:
    if len(configs) != len(dashboards):
        raise RuntimeError("HK QDII target and dashboard counts differ.")
    core_rows = overview.get("targets", [])
    if len(core_rows) != 21:
        raise RuntimeError(f"Expected 21 core targets before merge, found {len(core_rows)}.")
    for row in core_rows:
        row["route"] = f"/topic/{row['slug']}"

    hk_rows = [
        build_overview_row(config, dashboard)
        for config, dashboard in zip(configs, dashboards, strict=True)
    ]
    all_rows = core_rows + hk_rows
    dates = {row["latestDate"] for row in all_rows}
    if len(dates) != 1:
        raise RuntimeError(f"Unified overview dates differ: {sorted(dates)}.")

    overview["targets"] = all_rows
    overview["meta"].update(
        {
            "targetCount": len(all_rows),
            "coreTargetCount": len(core_rows),
            "hkQdiiCount": len(hk_rows),
            "etfCount": sum(row["kind"] in {"etf", "hk_qdii"} for row in all_rows),
            "indexCount": sum(row["kind"] == "index" for row in all_rows),
            "source": "Tushare Pro + Hang Seng Indexes + Tencent Securities",
        }
    )
    return overview


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge HK QDII targets into production overview.")
    parser.add_argument("--overview", type=Path, default=DEFAULT_OVERVIEW)
    parser.add_argument("--targets", type=Path, default=DEFAULT_TARGETS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    overview = read_json(args.overview)
    configs = read_json(args.targets)
    dashboards = [read_json(ROOT / config["dataFile"]) for config in configs]
    merged = merge_overview(overview, configs, dashboards)
    args.overview.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"Merged {merged['meta']['hkQdiiCount']} HK QDII targets; "
        f"unified target count={merged['meta']['targetCount']}."
    )


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
import unittest
from pathlib import Path

import pandas as pd

from generate_hk_qdii_dashboard_data import (
    evaluate_hk_breadth,
    evaluate_hk_leader_event,
    evaluate_low_position,
)
from merge_hk_qdii_overview import merge_overview


class HkQdiiStrategyBehaviorTests(unittest.TestCase):
    def test_hk_connect_snapshot_uses_tracking_index_directly(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "data"
            / "hk_qdii"
            / "513230-sh.json"
        )
        snapshot = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(snapshot["meta"]["structureSource"], "tracking_index")
        self.assertEqual(snapshot["target"]["feederCode"], "017832.OF")
        self.assertEqual(snapshot["target"]["code"], "513230.SH")
        self.assertEqual(snapshot["target"]["indexCode"], "931454.CSI")
        self.assertEqual(len(snapshot["constituents"]), 10)
        self.assertTrue(
            all(row["weight"] > 0 for row in snapshot["constituents"])
        )
        self.assertTrue(snapshot["meta"]["productionIntegrated"])

    def test_merges_hk_targets_into_unified_overview(self) -> None:
        root = Path(__file__).resolve().parents[1]
        core_overview = json.loads(
            (root / "data" / "overview.json").read_text(encoding="utf-8")
        )
        core_overview["targets"] = [
            row
            for row in core_overview["targets"]
            if row["kind"] != "hk_qdii"
        ]
        configs = json.loads(
            (root / "hk_qdii_targets.json").read_text(encoding="utf-8")
        )
        dashboards = [
            json.loads((root / config["dataFile"]).read_text(encoding="utf-8"))
            for config in configs
        ]

        merged = merge_overview(core_overview, configs, dashboards)

        self.assertEqual(merged["meta"]["targetCount"], 23)
        self.assertEqual(merged["meta"]["coreTargetCount"], 21)
        self.assertEqual(merged["meta"]["hkQdiiCount"], 2)
        self.assertEqual(
            {row["route"] for row in merged["targets"] if row["kind"] == "hk_qdii"},
            {"/hk-qdii/513970-sh", "/hk-qdii/513230-sh"},
        )

    def test_low_position_passes_on_long_stay_below_ma250(self) -> None:
        result = evaluate_low_position(
            below_ma250_days=60,
            below_ma250_ten_days=8,
        )

        self.assertTrue(result["passed"])
        self.assertFalse(result["warning"])

    def test_low_position_warns_before_either_path_passes(self) -> None:
        result = evaluate_low_position(
            below_ma250_days=42,
            below_ma250_ten_days=10,
        )

        self.assertFalse(result["passed"])
        self.assertTrue(result["warning"])

    def test_secondary_constituent_event_cannot_strictly_confirm(self) -> None:
        daily = self._daily_with_recent_impulse()

        event = evaluate_hk_leader_event(
            code="02020.HK",
            name="安踏体育",
            rank=4,
            as_of="20260724",
            daily=daily,
        )

        self.assertIsNotNone(event)
        assert event is not None
        self.assertTrue(event["qualified"])
        self.assertFalse(event["strictQualified"])

    def test_stale_constituent_cannot_confirm_leader_layer(self) -> None:
        daily = self._daily_with_recent_impulse().iloc[:-2].copy()

        event = evaluate_hk_leader_event(
            code="00669.HK",
            name="创科实业",
            rank=1,
            as_of="20260724",
            daily=daily,
        )

        self.assertIsNotNone(event)
        assert event is not None
        self.assertFalse(event["dataFresh"])
        self.assertFalse(event["qualified"])
        self.assertFalse(event["strictQualified"])

    def test_stale_constituent_is_excluded_from_group_breadth(self) -> None:
        rows = [
            {
                "dataFresh": index < 9,
                "aboveMa60": True,
                "ret5d": 2.0,
            }
            for index in range(10)
        ]

        breadth = evaluate_hk_breadth(rows)

        self.assertEqual(breadth["freshCount"], 9)
        self.assertEqual(breadth["aboveMa60Count"], 9)
        self.assertEqual(breadth["positive5dCount"], 9)
        self.assertFalse(breadth["confirmed"])

    @staticmethod
    def _daily_with_recent_impulse() -> pd.DataFrame:
        dates = pd.bdate_range("2025-12-01", periods=170)
        closes = [100.0 + index * 0.02 for index in range(len(dates))]
        event_index = len(dates) - 3
        closes[event_index] = closes[event_index - 1] * 1.06
        closes[event_index + 1] = closes[event_index] * 1.01
        closes[event_index + 2] = closes[event_index + 1] * 1.005
        frame = pd.DataFrame(
            {
                "trade_date": dates.strftime("%Y%m%d"),
                "close": closes,
                "volume": 1_000_000,
            }
        )
        frame.loc[frame.index[-1], "trade_date"] = "20260724"
        frame.loc[frame.index[-2], "trade_date"] = "20260723"
        frame.loc[frame.index[-3], "trade_date"] = "20260722"
        frame.loc[frame.index[-4], "trade_date"] = "20260721"
        return frame


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


SANDBOX_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SANDBOX_DIR))

from check_tushare_readiness import (
    build_readiness_universe,
    extend_with_hk_qdii,
    frame_has_trade_date,
    live_overview_is_current,
)
from trading_calendar import (
    completed_calendar_end,
    latest_completed_trade_date,
    latest_unpublished_trade_date,
)

ROOT_DIR = SANDBOX_DIR.parent
sys.path.insert(0, str(ROOT_DIR))
from run_etf_constituent_workflow import _default_end_date


class ReadinessUniverseBehaviorTest(unittest.TestCase):
    def test_resolves_every_etf_and_direct_index(self) -> None:
        targets = [
            {"code": "510001.SH", "kind": "etf"},
            {"code": "159001.SZ", "kind": "etf"},
            {"code": "931001.CSI", "kind": "index"},
        ]
        metadata = [
            {"ts_code": "510001.SH", "index_code": "000001.SH"},
            {"ts_code": "159001.SZ", "index_code": "399001.SZ"},
        ]

        universe = build_readiness_universe(targets, metadata)

        self.assertEqual(
            universe["etf_targets"],
            ["159001.SZ", "510001.SH"],
        )
        self.assertEqual(
            universe["tracking_indexes"],
            ["000001.SH", "399001.SZ", "931001.CSI"],
        )
        self.assertEqual(universe["unresolved_etfs"], [])

    def test_deduplicates_shared_tracking_indexes(self) -> None:
        targets = [
            {"code": "510001.SH", "kind": "etf"},
            {"code": "159001.SZ", "kind": "etf"},
        ]
        metadata = [
            {"ts_code": "510001.SH", "index_code": "000001.SH"},
            {"ts_code": "159001.SZ", "index_code": "000001.SH"},
        ]

        universe = build_readiness_universe(targets, metadata)

        self.assertEqual(universe["tracking_indexes"], ["000001.SH"])

    def test_missing_etf_tracking_metadata_is_reported(self) -> None:
        targets = [{"code": "510001.SH", "kind": "etf"}]

        universe = build_readiness_universe(targets, [])

        self.assertEqual(universe["unresolved_etfs"], ["510001.SH"])
        self.assertEqual(universe["tracking_indexes"], [])

    def test_rejects_unsupported_target_kind(self) -> None:
        targets = [{"code": "600000.SH", "kind": "stock"}]

        with self.assertRaises(ValueError):
            build_readiness_universe(targets, [])

    def test_extends_readiness_with_hk_etfs_indexes_and_benchmark(self) -> None:
        core = {
            "etf_targets": ["510001.SH"],
            "tracking_indexes": ["000001.SH"],
            "unresolved_etfs": [],
        }
        hk_targets = [
            {
                "code": "513970.SH",
                "kind": "hk_qdii",
                "readinessIndexCode": None,
                "benchmarkCode": "HSI",
            },
            {
                "code": "513230.SH",
                "kind": "hk_qdii",
                "readinessIndexCode": "931454.CSI",
                "benchmarkCode": "HSI",
            },
        ]

        universe = extend_with_hk_qdii(core, hk_targets)

        self.assertEqual(
            universe["etf_targets"],
            ["510001.SH", "513230.SH", "513970.SH"],
        )
        self.assertEqual(
            universe["tracking_indexes"],
            ["000001.SH", "931454.CSI"],
        )
        self.assertEqual(universe["global_indexes"], ["HSI"])


class TradeDateBehaviorTest(unittest.TestCase):
    CALENDAR = [
        {"cal_date": "20260730", "is_open": 1},
        {"cal_date": "20260731", "is_open": 1},
        {"cal_date": "20260801", "is_open": 0},
        {"cal_date": "20260802", "is_open": 0},
        {"cal_date": "20260803", "is_open": 1},
    ]

    def test_requires_target_date_and_minimum_row_count(self) -> None:
        frame = pd.DataFrame(
            {
                "trade_date": ["20260723", "20260724"],
                "close": [1.0, 1.1],
            }
        )

        self.assertTrue(frame_has_trade_date(frame, "20260724"))
        self.assertFalse(frame_has_trade_date(frame, "20260725"))
        self.assertFalse(
            frame_has_trade_date(frame, "20260724", minimum_rows=3)
        )

    def test_weekend_uses_previous_completed_trade_date(self) -> None:
        saturday = datetime(2026, 8, 1, 0, 14, tzinfo=ZoneInfo("Asia/Shanghai"))

        self.assertEqual(completed_calendar_end(saturday), "20260731")
        self.assertEqual(
            latest_completed_trade_date(self.CALENDAR, saturday),
            "20260731",
        )

    def test_readiness_selects_latest_unpublished_trade_date(self) -> None:
        monday_evening = datetime(2026, 8, 3, 22, 25, tzinfo=ZoneInfo("Asia/Shanghai"))

        self.assertEqual(
            latest_unpublished_trade_date(
                self.CALENDAR,
                "20260730",
                monday_evening,
            ),
            "20260803",
        )
        self.assertEqual(
            latest_unpublished_trade_date(
                self.CALENDAR,
                "20260731",
                monday_evening,
            ),
            "20260803",
        )

    def test_orchestrator_default_date_uses_trade_calendar(self) -> None:
        saturday = datetime(2026, 8, 1, 0, 14, tzinfo=ZoneInfo("Asia/Shanghai"))

        self.assertEqual(_default_end_date(saturday, self.CALENDAR), "20260731")


class LiveOverviewBehaviorTest(unittest.TestCase):
    def test_same_day_live_overview_short_circuits_readiness(self) -> None:
        overview = {
            "targets": [
                {"latestDate": "20260724"},
                {"latestDate": "20260724"},
            ]
        }

        self.assertTrue(
            live_overview_is_current(overview, "20260724")
        )

    def test_older_live_overview_does_not_short_circuit_readiness(self) -> None:
        overview = {
            "targets": [
                {"latestDate": "20260723"},
                {"latestDate": "20260723"},
            ]
        }

        self.assertFalse(
            live_overview_is_current(overview, "20260724")
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


SANDBOX_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SANDBOX_DIR))

from check_tushare_readiness import (
    build_readiness_universe,
    frame_has_trade_date,
)


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


class TradeDateBehaviorTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()

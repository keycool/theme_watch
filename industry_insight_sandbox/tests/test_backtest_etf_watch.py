from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


SANDBOX_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SANDBOX_DIR))

from backtest_etf_watch import (
    add_forward_outcomes,
    add_indicators,
    build_baseline_rows,
    build_lifecycle_series,
    build_snapshot_map,
    latest_snapshot,
    TargetSpec,
    validate_lifecycle_replay,
)


class EtfWatchBacktestBehaviorTest(unittest.TestCase):
    def test_lifecycle_vector_replay_matches_production_engine(self) -> None:
        closes = []
        for index in range(900):
            if index < 350:
                closes.append(200 - index * 0.18)
            elif index < 700:
                closes.append(137 + (index % 30) * 0.03)
            else:
                closes.append(138 + (index - 700) * 0.20)
        daily = pd.DataFrame(
            {
                "trade_date": [f"{20200000 + index + 101:08d}" for index in range(900)],
                "close": closes,
                "open": closes,
                "amount": 1.0,
            }
        )
        prepared = add_indicators(daily)
        replay = build_lifecycle_series(prepared)

        validate_lifecycle_replay(prepared, replay, "SYNTHETIC")

    def test_lifecycle_replay_is_unchanged_by_future_rows(self) -> None:
        daily = pd.DataFrame(
            {
                "trade_date": [f"2025{index + 101:04d}" for index in range(400)],
                "close": [100 + (index % 50) * 0.1 for index in range(400)],
                "open": [100] * 400,
                "amount": [1] * 400,
            }
        )
        prepared = add_indicators(daily)
        prefix = build_lifecycle_series(prepared.iloc[:350]).iloc[-1].to_dict()
        full_at_prefix = build_lifecycle_series(prepared).iloc[349].to_dict()

        self.assertEqual(prefix, full_at_prefix)

    def test_weight_snapshot_never_uses_future_month(self) -> None:
        weights = pd.DataFrame(
            [
                {"trade_date": date, "con_code": code, "weight": weight}
                for date in ("20260131", "20260228")
                for code, weight in (("A.SH", 60), ("B.SH", 40))
            ]
        )
        snapshots = build_snapshot_map(weights)
        before, cursor = latest_snapshot(snapshots, "20260130", -1)
        january, cursor = latest_snapshot(snapshots, "20260215", cursor)

        self.assertIsNone(before)
        self.assertEqual(january["date"], "20260131")

    def test_forward_outcome_uses_next_open_for_executable_return(self) -> None:
        price = pd.DataFrame(
            {
                "trade_date": [f"2026010{day}" for day in range(1, 8)],
                "open": [10, 11, 12, 13, 14, 15, 16],
                "close": [10, 12, 13, 14, 15, 16, 17],
            }
        )
        event = {
            "code": "TEST.SH",
            "name": "Test",
            "engine": "core",
            "eventType": "signal",
            "signalDate": "20260101",
            "signalPosition": 0,
            "primaryLabel": "观察中",
        }
        outcome = add_forward_outcomes(event, price, price, price)

        self.assertEqual(outcome["d5NextOpenEntryDate"], "20260102")

    def test_unconditional_baseline_does_not_require_structure_on_sample_day(self) -> None:
        dates = [f"202601{day:02d}" for day in range(1, 31)]
        price = pd.DataFrame(
            {
                "trade_date": dates,
                "open": range(100, 130),
                "close": range(100, 130),
            }
        )
        history = pd.DataFrame(
            {
                "trade_date": dates,
                "name": ["Test"] * 30,
                "engine": ["core"] * 30,
                "primary_label": ["未启动"] * 30,
                "structure_complete": [False] * 5 + [True] + [False] * 24,
            }
        )
        spec = TargetSpec("TEST.SH", "Test", "index", "core", "TEST.SH", None, "BM")
        rows = build_baseline_rows(
            {spec.code: history},
            {spec.code: price},
            {"BM": price},
            {spec.code: spec},
        )
        unconditional_dates = [
            row["signalDate"]
            for row in rows
            if row["eventType"] == "baseline_unconditional_every_5d"
        ]

        self.assertEqual(unconditional_dates[:2], ["20260106", "20260112"])
        self.assertFalse(bool(history.iloc[11]["structure_complete"]))


if __name__ == "__main__":
    unittest.main()

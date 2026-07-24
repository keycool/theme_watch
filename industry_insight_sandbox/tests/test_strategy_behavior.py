from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


SANDBOX_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SANDBOX_DIR))

from generate_dashboard_data import (
    evaluate_breakout_state,
    evaluate_limit_event,
    evaluate_structure_state,
    limit_threshold,
)


def daily(rows: list[tuple[str, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["trade_date", "close", "pct_chg"])


def structure_frame(
    *,
    below_days: int = 0,
    deep_days: int = 0,
    row_count: int = 120,
) -> pd.DataFrame:
    close = [100.0] * row_count
    for index in range(min(below_days, row_count)):
        close[index] = 95.0
    for index in range(min(deep_days, row_count)):
        close[index] = 90.0
    return pd.DataFrame({"close": close, "ma250": [100.0] * row_count})


def breakout_frame(
    *,
    funding_ranks: list[float],
    closes: list[float] | None = None,
    ma60: list[float] | None = None,
    ma250: list[float] | None = None,
) -> pd.DataFrame:
    row_count = len(funding_ranks)
    return pd.DataFrame(
        {
            "close": closes or [100.0] * row_count,
            "ma60": ma60 or [100.0] * row_count,
            "ma250": ma250 or [100.0] * row_count,
            "amount_ratio20": [1.0] * row_count,
            "absorption_rank_pct": funding_ranks,
        }
    )


class LimitEventBehaviorTest(unittest.TestCase):
    def test_stale_own_tail_event_is_outside_market_window(self) -> None:
        market_dates = [
            "20260701",
            "20260702",
            "20260703",
            "20260706",
            "20260707",
            "20260708",
            "20260709",
            "20260710",
            "20260713",
            "20260714",
            "20260715",
            "20260716",
            "20260717",
        ]
        component = daily(
            [
                ("20260701", 10.0, 9.5),
                ("20260702", 10.3, 3.0),
                ("20260703", 10.2, -1.0),
            ]
        )

        event = evaluate_limit_event(
            code="600000.SH",
            name="stale sample",
            rank=1,
            market_trade_dates=market_dates,
            daily=component,
        )

        self.assertIsNone(event)

    def test_recent_event_is_not_qualified_when_component_is_stale(self) -> None:
        market_dates = [
            "20260713",
            "20260714",
            "20260715",
            "20260716",
            "20260717",
        ]
        component = daily(
            [
                ("20260713", 9.0, 0.0),
                ("20260714", 10.0, 9.5),
                ("20260715", 10.2, 2.0),
                ("20260716", 10.3, 1.0),
            ]
        )

        event = evaluate_limit_event(
            code="600000.SH",
            name="stale latest sample",
            rank=1,
            market_trade_dates=market_dates,
            daily=component,
        )

        self.assertIsNotNone(event)
        self.assertFalse(event["dataFresh"])
        self.assertEqual(event["componentLatestDate"], "20260716")
        self.assertFalse(event["qualified"])

    def test_missing_next_market_day_cannot_confirm_continuation(self) -> None:
        market_dates = [
            "20260713",
            "20260714",
            "20260715",
            "20260716",
            "20260717",
        ]
        component = daily(
            [
                ("20260713", 9.0, 0.0),
                ("20260714", 10.0, 9.5),
                ("20260716", 10.2, 2.0),
                ("20260717", 10.3, 1.0),
            ]
        )

        event = evaluate_limit_event(
            code="600000.SH",
            name="missing next day sample",
            rank=1,
            market_trade_dates=market_dates,
            daily=component,
        )

        self.assertIsNotNone(event)
        self.assertTrue(event["dataFresh"])
        self.assertEqual(event["nextMarketDate"], "20260715")
        self.assertFalse(event["continuationKnown"])
        self.assertFalse(event["qualified"])

    def test_exact_limit_threshold_can_confirm_fresh_strict_leader(self) -> None:
        market_dates = [
            "20260713",
            "20260714",
            "20260715",
            "20260716",
            "20260717",
        ]
        component = daily(
            [
                ("20260713", 9.0, 0.0),
                ("20260714", 10.0, 9.5),
                ("20260715", 10.2, 2.0),
                ("20260716", 10.1, -1.0),
                ("20260717", 10.4, 3.0),
            ]
        )

        event = evaluate_limit_event(
            code="600000.SH",
            name="valid strict leader sample",
            rank=1,
            market_trade_dates=market_dates,
            daily=component,
        )

        self.assertIsNotNone(event)
        self.assertTrue(event["dataFresh"])
        self.assertTrue(event["continuationKnown"])
        self.assertTrue(event["continuationOk"])
        self.assertTrue(event["latestRetained"])
        self.assertTrue(event["qualified"])

    def test_rows_after_target_date_do_not_enter_the_decision(self) -> None:
        market_dates = [
            "20260713",
            "20260714",
            "20260715",
            "20260716",
            "20260717",
        ]
        component = daily(
            [
                ("20260713", 10.0, 9.5),
                ("20260714", 10.2, 2.0),
                ("20260715", 10.1, -1.0),
                ("20260716", 10.3, 2.0),
                ("20260717", 10.4, 1.0),
                ("20260720", 8.0, -20.0),
            ]
        )

        event = evaluate_limit_event(
            code="600000.SH",
            name="lookahead control sample",
            rank=1,
            market_trade_dates=market_dates,
            daily=component,
        )

        self.assertIsNotNone(event)
        self.assertEqual(event["componentLatestDate"], "20260717")
        self.assertEqual(event["marketWindowEnd"], "20260717")
        self.assertTrue(event["latestRetained"])
        self.assertTrue(event["qualified"])

    def test_secondary_leader_uses_three_market_trade_days(self) -> None:
        market_dates = [
            "20260713",
            "20260714",
            "20260715",
            "20260716",
            "20260717",
        ]
        component = daily(
            [
                ("20260713", 10.0, 9.5),
                ("20260714", 10.2, 2.0),
                ("20260715", 10.3, 1.0),
                ("20260716", 10.4, 1.0),
                ("20260717", 10.5, 1.0),
            ]
        )

        event = evaluate_limit_event(
            code="600000.SH",
            name="secondary window sample",
            rank=4,
            market_trade_dates=market_dates,
            daily=component,
        )

        self.assertIsNone(event)

    def test_board_specific_limit_threshold_boundaries(self) -> None:
        self.assertEqual(limit_threshold("600000.SH"), 9.5)
        self.assertEqual(limit_threshold("300001.SZ"), 19.5)
        self.assertEqual(limit_threshold("688001.SH"), 19.5)
        self.assertEqual(limit_threshold("830001.BJ"), 29.5)
        self.assertEqual(limit_threshold("430001.BJ"), 29.5)


class StructureBehaviorTest(unittest.TestCase):
    def test_path_a_warning_and_pass_thresholds_are_inclusive(self) -> None:
        warning = evaluate_structure_state(structure_frame(below_days=40))
        passed = evaluate_structure_state(structure_frame(below_days=60))

        self.assertTrue(warning["warning"])
        self.assertFalse(warning["passed"])
        self.assertTrue(passed["passed"])
        self.assertFalse(passed["warning"])

    def test_path_b_warning_and_pass_thresholds_are_inclusive(self) -> None:
        warning = evaluate_structure_state(structure_frame(deep_days=12))
        passed = evaluate_structure_state(structure_frame(deep_days=24))

        self.assertTrue(warning["warning"])
        self.assertFalse(warning["passed"])
        self.assertTrue(passed["passed"])
        self.assertFalse(passed["warning"])

    def test_incomplete_120_day_window_cannot_warn_or_pass(self) -> None:
        state = evaluate_structure_state(
            structure_frame(below_days=119, deep_days=119, row_count=119)
        )

        self.assertFalse(state["complete"])
        self.assertFalse(state["warning"])
        self.assertFalse(state["passed"])


class BreakoutBehaviorTest(unittest.TestCase):
    def test_equal_ma_boundaries_and_exact_funding_threshold_confirm(self) -> None:
        state = evaluate_breakout_state(
            breakout_frame(funding_ranks=[0.80, 0.80, 0.80])
        )

        self.assertTrue(state["ma60Watch"])
        self.assertTrue(state["holdTwoDays"])
        self.assertTrue(state["fundingConfirmed"])
        self.assertTrue(state["confirmed"])

    def test_one_funding_day_below_threshold_blocks_confirmation(self) -> None:
        state = evaluate_breakout_state(
            breakout_frame(funding_ranks=[0.80, 0.7999, 0.80])
        )

        self.assertTrue(state["holdTwoDays"])
        self.assertFalse(state["fundingConfirmed"])
        self.assertTrue(state["emerged"])
        self.assertFalse(state["confirmed"])

    def test_missing_required_market_days_cannot_confirm(self) -> None:
        state = evaluate_breakout_state(breakout_frame(funding_ranks=[0.99]))

        self.assertFalse(state["holdTwoDays"])
        self.assertFalse(state["fundingConfirmed"])
        self.assertFalse(state["confirmed"])

    def test_ma60_equality_counts_as_breakout_today(self) -> None:
        state = evaluate_breakout_state(
            breakout_frame(
                funding_ranks=[0.10, 0.10],
                closes=[99.0, 100.0],
                ma60=[100.0, 100.0],
            )
        )

        self.assertTrue(state["ma60Watch"])
        self.assertTrue(state["ma60BreakoutToday"])


if __name__ == "__main__":
    unittest.main()

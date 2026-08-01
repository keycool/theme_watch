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
    evaluate_short_term_rhythm,
    evaluate_strategy_label,
    evaluate_structure_state,
    limit_threshold,
)


def daily(rows: list[tuple[str, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["trade_date", "close", "pct_chg"])


def structure_frame(
    *,
    effective_low_days: int = 0,
    shallow_below_days: int = 0,
    deep_days: int = 0,
    row_count: int = 120,
) -> pd.DataFrame:
    close = [100.0] * row_count
    for index in range(min(shallow_below_days, row_count)):
        close[index] = 99.0
    for index in range(min(effective_low_days, row_count)):
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
        warning = evaluate_structure_state(
            structure_frame(effective_low_days=40)
        )
        passed = evaluate_structure_state(
            structure_frame(effective_low_days=60)
        )

        self.assertTrue(warning["warning"])
        self.assertFalse(warning["passed"])
        self.assertEqual(warning["belowMa250FiveDays"], 40)
        self.assertTrue(passed["passed"])
        self.assertFalse(passed["warning"])

    def test_shallow_yearline_oscillation_is_not_effective_low_position(self) -> None:
        state = evaluate_structure_state(
            structure_frame(shallow_below_days=95)
        )

        self.assertEqual(state["belowMa250Days"], 95)
        self.assertEqual(state["belowMa250FiveDays"], 0)
        self.assertFalse(state["warning"])
        self.assertFalse(state["passed"])

    def test_path_b_requires_both_low_duration_and_deep_days(self) -> None:
        recent_drop = evaluate_structure_state(
            structure_frame(shallow_below_days=18, deep_days=12)
        )
        warning = evaluate_structure_state(
            structure_frame(shallow_below_days=24, deep_days=12)
        )
        passed = evaluate_structure_state(
            structure_frame(shallow_below_days=40, deep_days=24)
        )

        self.assertFalse(recent_drop["warning"])
        self.assertFalse(recent_drop["passed"])
        self.assertTrue(warning["warning"])
        self.assertFalse(warning["passed"])
        self.assertTrue(passed["passed"])
        self.assertFalse(passed["warning"])

    def test_incomplete_120_day_window_cannot_warn_or_pass(self) -> None:
        state = evaluate_structure_state(
            structure_frame(
                effective_low_days=119,
                deep_days=119,
                row_count=119,
            )
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
        self.assertEqual(state["fundingRanks"], [0.80, 0.80, 0.80])
        self.assertEqual(state["fundingQualifiedDays"], 3)
        self.assertTrue(state["fundingConfirmed"])
        self.assertTrue(state["confirmed"])

    def test_one_funding_day_below_threshold_blocks_confirmation(self) -> None:
        state = evaluate_breakout_state(
            breakout_frame(funding_ranks=[0.80, 0.7999, 0.80])
        )

        self.assertTrue(state["holdTwoDays"])
        self.assertEqual(state["fundingRanks"], [0.80, 0.7999, 0.80])
        self.assertEqual(state["fundingQualifiedDays"], 2)
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

    def test_ma60_observation_window_boundary_is_inclusive(self) -> None:
        boundary = evaluate_breakout_state(
            breakout_frame(
                funding_ranks=[0.10],
                closes=[97.0],
                ma60=[100.0],
            )
        )
        outside = evaluate_breakout_state(
            breakout_frame(
                funding_ranks=[0.10],
                closes=[96.99],
                ma60=[100.0],
            )
        )

        self.assertFalse(boundary["ma60Watch"])
        self.assertTrue(boundary["ma60Near"])
        self.assertFalse(outside["ma60Near"])


class StrategyLabelBehaviorTest(unittest.TestCase):
    def label(self, **overrides: bool) -> str:
        inputs = {
            "trend_extension": False,
            "structure_passed": False,
            "structure_warning": False,
            "breakout_confirmed": False,
            "breakout_emerged": False,
            "leader_confirmed": False,
            "leader_group_monitor": False,
            "ma60_near": False,
        }
        inputs.update(overrides)
        return evaluate_strategy_label(**inputs)

    def test_side_signals_cannot_enter_observation_without_structure(self) -> None:
        self.assertEqual(
            self.label(
                breakout_emerged=True,
                leader_confirmed=True,
                leader_group_monitor=True,
            ),
            "未启动",
        )

    def test_structure_without_ma60_window_stays_unstarted(self) -> None:
        self.assertEqual(self.label(structure_warning=True), "未启动")

    def test_structure_and_ma60_window_enter_observation(self) -> None:
        self.assertEqual(
            self.label(structure_warning=True, ma60_near=True),
            "观察中",
        )

    def test_later_states_remain_layered_on_structure_pass(self) -> None:
        self.assertEqual(
            self.label(
                structure_passed=True,
                breakout_emerged=True,
                leader_group_monitor=True,
            ),
            "接近启动",
        )
        self.assertEqual(
            self.label(
                structure_passed=True,
                breakout_confirmed=True,
                leader_confirmed=True,
            ),
            "启动确认",
        )


class ShortTermRhythmBehaviorTest(unittest.TestCase):
    def rhythm(
        self,
        *,
        close: float,
        ma20: float,
        ma60: float,
        prior_ma20: float,
    ) -> str:
        frame = pd.DataFrame(
            {
                "close": [close] * 6,
                "ma20": [prior_ma20] * 5 + [ma20],
                "ma60": [ma60] * 6,
            }
        )
        return evaluate_short_term_rhythm(frame)

    def test_classifies_ma20_as_a_diagnostic_rhythm_label(self) -> None:
        cases = {
            "短期转强": dict(close=105, ma20=103, ma60=100, prior_ma20=99),
            "低位反弹": dict(close=100, ma20=99, ma60=102, prior_ma20=100),
            "上升回踩": dict(close=100, ma20=102, ma60=101, prior_ma20=100),
            "短期转弱": dict(close=95, ma20=98, ma60=100, prior_ma20=100),
            "震荡整理": dict(close=99, ma20=100, ma60=102, prior_ma20=99),
        }
        for expected, inputs in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(self.rhythm(**inputs), expected)


if __name__ == "__main__":
    unittest.main()

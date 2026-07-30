from __future__ import annotations

import unittest

import pandas as pd

from moving_average_lifecycle import evaluate_moving_average_lifecycle


def lifecycle_frame() -> pd.DataFrame:
    rows = 230
    frame = pd.DataFrame(
        {
            "trade_date": pd.bdate_range("2025-01-02", periods=rows).strftime(
                "%Y%m%d"
            ),
            "ma250": [100.0] * rows,
        }
    )
    frame["ma60"] = [
        105.0 if index < 10 else 99.0 - float(index % 8)
        for index in range(rows)
    ]
    frame["ma20"] = frame["ma60"] - 1.0
    frame["close"] = frame["ma20"] - 1.0

    frame.loc[190:199, "ma60"] = 91.0
    frame.loc[190:199, "ma20"] = 90.0
    frame.loc[190:199, "close"] = 90.5
    frame.loc[200:204, "ma60"] = 91.0
    frame.loc[200:204, "ma20"] = 90.0
    frame.loc[200:204, "close"] = 92.0
    frame.loc[205:, "ma60"] = 91.0
    frame.loc[205:, "ma20"] = 90.0
    frame.loc[205:, "close"] = 101.0
    return frame


class MovingAverageLifecycleTests(unittest.TestCase):
    def test_ma20_cross_is_only_a_warm_up_signal(self) -> None:
        result = evaluate_moving_average_lifecycle(lifecycle_frame().iloc[:191])

        self.assertEqual(result["label"], "短线转暖")
        self.assertIsNotNone(result["warmUpDate"])
        self.assertIsNone(result["initialStartDate"])
        self.assertEqual(result["capitalInterface"], "observe_only")

    def test_valid_ma60_cross_starts_the_initial_signal(self) -> None:
        result = evaluate_moving_average_lifecycle(lifecycle_frame().iloc[:201])

        self.assertEqual(result["label"], "初始启动")
        self.assertTrue(result["initialStartToday"])
        self.assertTrue(result["safetyMarginPassed"])
        self.assertGreaterEqual(result["separationPct"], 5.0)
        self.assertGreaterEqual(result["separationRankPct"], 70.0)
        self.assertEqual(result["capitalInterface"], "starter_position_eligible")

    def test_ma250_cross_confirms_the_trend_on_the_same_day(self) -> None:
        result = evaluate_moving_average_lifecycle(lifecycle_frame().iloc[:206])

        self.assertEqual(result["label"], "年线趋势确认")
        self.assertTrue(result["trendConfirmedToday"])
        self.assertTrue(result["trendConfirmedActive"])
        self.assertEqual(result["capitalInterface"], "scale_in_eligible")

    def test_future_rows_do_not_change_the_prior_initial_event(self) -> None:
        frame = lifecycle_frame()
        at_start = evaluate_moving_average_lifecycle(frame.iloc[:201])
        after_start = evaluate_moving_average_lifecycle(frame.iloc[:205])

        self.assertEqual(
            at_start["initialStartDate"],
            after_start["initialStartDate"],
        )
        self.assertEqual(
            at_start["initialStartDate"],
            frame.iloc[200]["trade_date"],
        )

    def test_absolute_safety_floor_blocks_a_shallow_separation(self) -> None:
        frame = lifecycle_frame().iloc[:201].copy()
        frame.loc[190:200, "ma60"] = 96.0
        frame.loc[190:200, "ma20"] = 95.0
        frame.loc[190:199, "close"] = 95.5
        frame.loc[200, "close"] = 97.0

        result = evaluate_moving_average_lifecycle(frame)

        self.assertFalse(result["safetyMarginPassed"])
        self.assertIsNone(result["initialStartDate"])
        self.assertNotEqual(result["label"], "初始启动")


if __name__ == "__main__":
    unittest.main()

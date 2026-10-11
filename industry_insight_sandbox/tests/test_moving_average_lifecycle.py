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

        self.assertEqual(result["stateCode"], "above_ma20")
        self.assertIsNotNone(result["ma20CrossUpDate"])
        self.assertIsNone(result["ma60CrossUpDate"])
        self.assertEqual(result["stateCode"], "above_ma20")

    def test_valid_ma60_cross_starts_the_initial_signal(self) -> None:
        result = evaluate_moving_average_lifecycle(lifecycle_frame().iloc[:201])

        self.assertEqual(result["stateCode"], "above_ma60")
        self.assertTrue(result["ma60CrossUpToday"])
        self.assertTrue(result["stateAboveMa60"])
        self.assertGreaterEqual(result["separationPct"], 5.0)
        self.assertGreaterEqual(result["separationRankPct"], 70.0)
        self.assertTrue(result["stateAboveMa60"])

    def test_ma250_cross_confirms_the_trend_on_the_same_day(self) -> None:
        result = evaluate_moving_average_lifecycle(lifecycle_frame().iloc[:206])

        self.assertEqual(result["stateCode"], "above_ma250")
        self.assertTrue(result["aboveMa250Today"])
        self.assertTrue(result["stateAboveMa250"])
        self.assertTrue(result["stateAboveMa250"])

    def test_future_rows_do_not_change_the_prior_initial_event(self) -> None:
        frame = lifecycle_frame()
        at_start = evaluate_moving_average_lifecycle(frame.iloc[:201])
        after_start = evaluate_moving_average_lifecycle(frame.iloc[:205])

        self.assertEqual(
            at_start["ma60CrossUpDate"],
            after_start["ma60CrossUpDate"],
        )
        self.assertEqual(
            at_start["ma60CrossUpDate"],
            frame.iloc[200]["trade_date"],
        )

    def test_absolute_safety_floor_blocks_a_shallow_separation(self) -> None:
        frame = lifecycle_frame().iloc[:201].copy()
        frame.loc[190:200, "ma60"] = 96.0
        frame.loc[190:200, "ma20"] = 95.0
        frame.loc[190:199, "close"] = 95.5
        frame.loc[200, "close"] = 97.0

        result = evaluate_moving_average_lifecycle(frame)

        # 几何读数只认收盘价与均线：97 > ma60(96) → above_ma60，
        # 不受安全边际门槛影响（安全边际是资格语义，不再是几何位置的一部分）。
        self.assertEqual(result["stateCode"], "above_ma60")
        # 资格语义仍被安全边际 / 收敛门槛挡住：上穿事件不成立。
        self.assertFalse(result["stateAboveMa60"])
        self.assertIsNone(result["ma60CrossUpDate"])


if __name__ == "__main__":
    unittest.main()

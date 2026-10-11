from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd


SANDBOX_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SANDBOX_DIR))

from backtest_execution_discipline import (
    ExecutionVariant,
    simulate_execution_discipline,
)


def make_dates(count: int) -> list[str]:
    return [f"202601{index + 1:02d}" for index in range(count)]


def make_history(
    code: str,
    dates: list[str],
    *,
    signals: set[str],
    breakout_dates: set[str] | None = None,
    below_ma60_dates: set[str] | None = None,
) -> pd.DataFrame:
    breakout_dates = breakout_dates or set()
    below_ma60_dates = below_ma60_dates or set()
    return pd.DataFrame(
        [
            {
                "code": code,
                "name": code,
                "trade_date": date,
                "initial_start_today": date in signals,
                "entry_guard_passed": True,
                "breakout_pass": date in breakout_dates,
                "funding_min3": 0.9 if date in breakout_dates else 0.5,
                "trend_confirmed_today": False,
                "trend_confirmed_active": False,
                "leader_pass": False,
                "close": 80.0 if date in below_ma60_dates else 100.0,
                "ma60": 90.0,
            }
            for date in dates
        ]
    )


def make_prices(dates: list[str], close: float = 100.0) -> pd.DataFrame:
    return pd.DataFrame(
        {"trade_date": dates, "open": [close] * len(dates), "close": [close] * len(dates)}
    )


class ExecutionDisciplineBacktestTest(unittest.TestCase):
    def simulate(
        self,
        histories: dict[str, pd.DataFrame],
        dates: list[str],
        variant: ExecutionVariant,
        *,
        max_positions: int = 2,
    ) -> dict:
        prices = {code: make_prices(dates) for code in histories}
        specs = {
            code: SimpleNamespace(execution_code=code) for code in histories
        }
        return simulate_execution_discipline(
            histories,
            prices,
            specs,
            dates,
            make_prices(dates),
            variant,
            max_positions=max_positions,
            cost_bps_per_side=0,
        )

    def test_entry_uses_next_market_open(self) -> None:
        dates = make_dates(5)
        result = self.simulate(
            {"A": make_history("A", dates, signals={dates[0]})},
            dates,
            ExecutionVariant("fixed", False, fixed_holding_days=2),
        )

        self.assertEqual(result["trades"][0]["entryDate"], dates[1])

    def test_signal_does_not_reenter_while_position_is_open(self) -> None:
        dates = make_dates(8)
        result = self.simulate(
            {"A": make_history("A", dates, signals={dates[0], dates[2]})},
            dates,
            ExecutionVariant("ma60", True),
        )

        self.assertEqual(len(result["trades"]), 1)
        self.assertEqual(result["summary"]["alreadyHeldRejected"], 1)

    def test_unvalidated_position_exits_after_twenty_trade_days(self) -> None:
        dates = make_dates(25)
        result = self.simulate(
            {"A": make_history("A", dates, signals={dates[0]})},
            dates,
            ExecutionVariant("conditional", True, unvalidated_holding_days=20),
        )
        trade = result["trades"][0]

        self.assertEqual(trade["holdingTradeDays"], 20)
        self.assertEqual(trade["exitDate"], dates[21])
        self.assertEqual(trade["exitReason"], "unvalidated_timeout")

    def test_breakout_validation_extends_holding_until_ma60_failure(self) -> None:
        dates = make_dates(28)
        result = self.simulate(
            {
                "A": make_history(
                    "A",
                    dates,
                    signals={dates[0]},
                    breakout_dates={dates[9]},
                    below_ma60_dates={dates[24]},
                )
            },
            dates,
            ExecutionVariant("conditional", True, unvalidated_holding_days=20),
        )
        trade = result["trades"][0]

        self.assertTrue(trade["breakoutValidated"])
        self.assertEqual(trade["exitDate"], dates[25])
        self.assertEqual(trade["exitReason"], "close_below_ma60")

    def test_same_day_capacity_prefers_already_validated_signal(self) -> None:
        dates = make_dates(5)
        result = self.simulate(
            {
                "A": make_history("A", dates, signals={dates[0]}),
                "B": make_history(
                    "B", dates, signals={dates[0]}, breakout_dates={dates[0]}
                ),
            },
            dates,
            ExecutionVariant("fixed", False, fixed_holding_days=2),
            max_positions=1,
        )

        self.assertEqual(result["trades"][0]["code"], "B")
        self.assertEqual(result["summary"]["capacityRejected"], 1)


if __name__ == "__main__":
    unittest.main()

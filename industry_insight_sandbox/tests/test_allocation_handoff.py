from __future__ import annotations

import sys
import unittest
from pathlib import Path


SANDBOX_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SANDBOX_DIR))

from build_allocation_handoff import (
    build_allocation_handoff,
    validate_allocation_handoff,
)


def chart(*, close: float = 101, ma60: float = 100, profit_protection: bool = False) -> list[dict]:
    rows = [
        {"date": f"202607{day:02d}", "close": 101, "ma20": 105 - day, "ma60": ma60}
        for day in range(1, 7)
    ]
    if profit_protection:
        rows[-2].update({"close": 98, "ma20": 100, "ma60": ma60})
        rows[-1].update({"close": 97, "ma20": 99, "ma60": ma60})
    else:
        rows[-1].update({"close": close, "ma20": 99, "ma60": ma60})
    return rows


def stages(all_passed: bool) -> list[dict]:
    return [
        {"id": stage_id, "passed": all_passed}
        for stage_id in ("structure", "breakout", "leader")
    ]


def topic(
    code: str,
    *,
    label: str = "观察中",
    capital_interface: str = "observe_only",
    initial_active: bool = False,
    initial_invalidated: bool = False,
    trend_active: bool = False,
    funding_confirmed: bool = False,
    crowding_hot: bool = False,
    all_stages_passed: bool = False,
    market_chart: list[dict] | None = None,
    stale_component: bool = False,
    history_ready: bool = True,
    weight_date: str = "20260731",
) -> dict:
    return {
        "meta": {
            "latestDate": "20260804",
            "weightDate": weight_date,
            "dataStart": "20190102",
            "historyTradeDayCount": 1840,
            "ma250ValidDayCount": 1591,
            "longCycleHistoryReady": history_ready,
        },
        "target": {"code": code},
        "summary": {
            "label": label,
            "fundingConfirmed": funding_confirmed,
            "crowdingHot": crowding_hot,
            "stagePassCount": 3 if all_stages_passed else 0,
            "absorptionRankPct": 80.0,
            "etfAmountRankPct": 50.0,
            "maLifecycle": {
                "label": "年线趋势确认" if trend_active else "初始启动",
                "capitalInterface": capital_interface,
                "initialStartToday": False,
                "initialStartActive": initial_active,
                "initialStartInvalidated": initial_invalidated,
                "trendConfirmedToday": False,
                "trendConfirmedActive": trend_active,
                "initialStartDate": "20260801" if initial_active or trend_active else None,
                "trendConfirmedDate": "20260804" if trend_active else None,
                "safetyMarginPassed": initial_active,
            },
        },
        "stages": stages(all_stages_passed),
        "chart": market_chart or chart(),
        "components": [
            {"dataFresh": True},
            {"dataFresh": True},
            {"dataFresh": not stale_component},
        ],
    }


class AllocationHandoffBehaviorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.codes = {
            "CANDIDATE.SH",
            "SCALE.SH",
            "STARTER.SH",
            "HOLD.SH",
            "PROTECT.SH",
            "EXIT.SH",
            "STALE.SH",
            "OBSERVE.SH",
        }
        self.overview = {
            "meta": {"generatedAt": "2026-08-04 22:30"},
            "targets": [
                {
                    "code": code,
                    "name": code,
                    "slug": code.lower().replace(".", "-"),
                    "kind": "etf",
                    "bucket": "test",
                    "route": f"/topic/{code.lower().replace('.', '-')}",
                    "latestDate": "20260804",
                    "order": order,
                    "label": "观察中",
                }
                for order, code in enumerate(sorted(self.codes), start=1)
            ],
        }

    def _build(self, topics: list[dict]) -> dict:
        return build_allocation_handoff(self.overview, topics, [])

    def test_maps_independent_position_stages_without_execution(self) -> None:
        handoff = self._build(
            [
                topic(
                    "CANDIDATE.SH",
                    label="接近启动",
                    market_chart=chart(close=98, ma60=100),
                ),
                topic(
                    "SCALE.SH",
                    capital_interface="scale_in_eligible",
                    trend_active=True,
                    funding_confirmed=True,
                    all_stages_passed=True,
                ),
                topic(
                    "STARTER.SH",
                    capital_interface="starter_position_eligible",
                    initial_active=True,
                ),
                topic("HOLD.SH", label="趋势延续"),
                topic(
                    "PROTECT.SH",
                    capital_interface="scale_in_eligible",
                    trend_active=True,
                    market_chart=chart(ma60=90, profit_protection=True),
                ),
                topic(
                    "EXIT.SH",
                    capital_interface="starter_position_eligible",
                    initial_active=True,
                    market_chart=chart(close=89, ma60=90),
                ),
                topic(
                    "STALE.SH",
                    capital_interface="starter_position_eligible",
                    initial_active=True,
                    stale_component=True,
                ),
                topic("OBSERVE.SH"),
            ]
        )
        by_code = {item["code"]: item for item in handoff["targets"]}

        expected = {
            "CANDIDATE.SH": ("candidate_entry", "candidate", 0.5),
            "SCALE.SH": ("scale_in_eligible", "confirmed", 2),
            "STARTER.SH": ("starter_eligible", "starter", 1),
            "HOLD.SH": ("hold_and_monitor", "extended", None),
            "PROTECT.SH": ("reduce_to_one_unit", "risk_protection", 1),
            "EXIT.SH": ("de_risk", "exit", 0),
            "STALE.SH": ("hold_and_monitor", "data_guard", None),
            "OBSERVE.SH": ("observe_only", "watch", 0),
        }
        for code, (action, stage, units) in expected.items():
            self.assertEqual(by_code[code]["action"], action)
            self.assertEqual(by_code[code]["positionSignal"]["stage"], stage)
            self.assertEqual(by_code[code]["targetAllocationUnits"], units)
            self.assertEqual(by_code[code]["positionSignal"]["referenceUnits"], units)

        self.assertTrue(by_code["CANDIDATE.SH"]["positionSignal"]["newEntryAllowed"])
        self.assertTrue(by_code["SCALE.SH"]["positionSignal"]["addPositionAllowed"])
        self.assertEqual(
            by_code["PROTECT.SH"]["positionSignal"]["riskAction"],
            "reduce_to_one_unit_if_held",
        )
        self.assertEqual(
            by_code["EXIT.SH"]["positionSignal"]["riskAction"],
            "exit_to_zero_if_held",
        )
        self.assertFalse(by_code["STALE.SH"]["guards"]["entryDataFresh"])
        self.assertFalse(by_code["STALE.SH"]["positionSignal"]["newEntryAllowed"])
        self.assertEqual(
            by_code["SCALE.SH"]["positionSignal"]["leaderConfirmationRole"],
            "industry_state_confirmation_only",
        )
        self.assertFalse(
            by_code["SCALE.SH"]["positionSignal"]["leaderStockChaseAllowed"]
        )
        self.assertTrue(by_code["SCALE.SH"]["guards"]["longCycleHistoryReady"])
        self.assertTrue(by_code["SCALE.SH"]["guards"]["weightFresh"])
        self.assertEqual(by_code["SCALE.SH"]["guards"]["weightAgeCalendarDays"], 4)
        self.assertFalse(handoff["meta"]["strategyExecutesOrders"])
        self.assertFalse(handoff["meta"]["positionSizingProvided"])
        self.assertFalse(handoff["meta"]["fixedCnyAmountProvided"])

    def test_ma250_cross_without_all_three_stages_cannot_scale(self) -> None:
        handoff = self._build(
            [
                topic(
                    "CANDIDATE.SH",
                    label="接近启动",
                    market_chart=chart(close=98, ma60=100),
                ),
                topic(
                    "SCALE.SH",
                    capital_interface="scale_in_eligible",
                    trend_active=True,
                    funding_confirmed=True,
                    all_stages_passed=False,
                ),
                topic("STARTER.SH"),
                topic("HOLD.SH"),
                topic("PROTECT.SH"),
                topic("EXIT.SH"),
                topic("STALE.SH"),
                topic("OBSERVE.SH"),
            ]
        )
        scale = next(item for item in handoff["targets"] if item["code"] == "SCALE.SH")

        self.assertEqual(scale["action"], "observe_only")
        self.assertEqual(scale["positionSignal"]["stage"], "watch")
        self.assertFalse(scale["positionSignal"]["addPositionAllowed"])

    def test_entry_ranking_includes_candidate_after_confirmed_and_starter(self) -> None:
        handoff = self._build(
            [
                topic(
                    "CANDIDATE.SH",
                    label="接近启动",
                    market_chart=chart(close=98, ma60=100),
                ),
                topic(
                    "SCALE.SH",
                    capital_interface="scale_in_eligible",
                    trend_active=True,
                    funding_confirmed=True,
                    all_stages_passed=True,
                ),
                topic(
                    "STARTER.SH",
                    capital_interface="starter_position_eligible",
                    initial_active=True,
                ),
                topic("HOLD.SH", label="趋势延续"),
                topic("PROTECT.SH"),
                topic("EXIT.SH"),
                topic("STALE.SH", stale_component=True),
                topic("OBSERVE.SH"),
            ]
        )
        by_code = {item["code"]: item for item in handoff["targets"]}

        self.assertEqual(by_code["SCALE.SH"]["entryPriorityRank"], 1)
        self.assertEqual(by_code["STARTER.SH"]["entryPriorityRank"], 2)
        self.assertEqual(by_code["CANDIDATE.SH"]["entryPriorityRank"], 3)
        self.assertIsNone(by_code["HOLD.SH"]["entryPriorityRank"])
        self.assertEqual(validate_allocation_handoff(handoff, self.codes, "20260804"), [])

    def test_history_and_weight_guards_block_entry_without_changing_primary_label(self) -> None:
        code = "GUARDED.SH"
        overview = {
            "meta": {"generatedAt": "2026-08-04 22:30"},
            "targets": [
                {
                    "code": code,
                    "name": code,
                    "slug": "guarded-sh",
                    "kind": "etf",
                    "bucket": "test",
                    "route": "/topic/guarded-sh",
                    "latestDate": "20260804",
                    "order": 1,
                    "label": "接近启动",
                }
            ],
        }
        guarded_topic = topic(
            code,
            label="接近启动",
            market_chart=chart(close=98, ma60=100),
            history_ready=False,
            weight_date="20260101",
        )
        handoff = build_allocation_handoff(overview, [guarded_topic], [])
        guarded = handoff["targets"][0]

        self.assertEqual(guarded["primaryLabel"], "接近启动")
        self.assertEqual(guarded["action"], "hold_and_monitor")
        self.assertEqual(guarded["positionSignal"]["stage"], "data_guard")
        self.assertFalse(guarded["guards"]["entryGuardPassed"])
        self.assertFalse(guarded["guards"]["longCycleHistoryReady"])
        self.assertFalse(guarded["guards"]["weightFresh"])
        self.assertIn("ENTRY_BLOCKED_INSUFFICIENT_HISTORY", guarded["reasonCodes"])
        self.assertIn("ENTRY_BLOCKED_STALE_WEIGHTS", guarded["reasonCodes"])
        self.assertEqual(validate_allocation_handoff(handoff, {code}, "20260804"), [])


if __name__ == "__main__":
    unittest.main()

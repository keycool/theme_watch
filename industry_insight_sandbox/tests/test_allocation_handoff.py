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
    approaching_start: bool = False,
    trend_extension: bool = False,
    initial_active: bool = False,
    initial_invalidated: bool = False,
    trend_active: bool = False,
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
            "stateInputs": {
                "belowMa250FiveDaysGe60": approaching_start,
                "belowMa250FiveDaysGe40": approaching_start,
                "belowMa250FiveDays": 60 if approaching_start else 0,
                "belowMa250TenDays": 0,
                "belowMa250FifteenDays": 0,
                "ma60WindowEntered": True,
                "ma60CrossUpEmerged": approaching_start,
                "ma60CrossUpConfirmed": trend_active,
                "leaderGroupMonitored": approaching_start,
                "leaderStreakMet": trend_active,
                "ma250ExceedPct15": trend_extension,
                "relativeExcessGe15Pct": False,
                "nearWindowHighBreadth": False,
                "breadthMa60Pct": 50.0,
                "breadthMa250Pct": 50.0,
                "closeToWindowHighPct": 90.0,
            },
            "stagePassCount": 3 if all_stages_passed else 0,
            "absorptionRankPct": 80.0,
            "etfAmountRankPct": 50.0,
            "maLifecycle": {
                "maStackCode": "MA20>MA60>MA250",
                "stateCode": "above_ma250" if trend_active else (
                    "above_ma60" if (initial_active or approaching_start)
                    else "below_ma20"
                ),
                "ma60CrossUpToday": False,
                "stateAboveMa60": initial_active,
                "ma60CrossUpInvalidated": initial_invalidated,
                "aboveMa250Today": False,
                "stateAboveMa250": trend_active,
                "ma60CrossUpDate": "20260801" if initial_active or trend_active else None,
                "firstAboveMa250Date": "20260804" if trend_active else None,
                "separationRankPct": 80.0,
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
                    "maStateCode": "below_ma20",
                }
                for order, code in enumerate(sorted(self.codes), start=1)
            ],
        }

    def _build(self, topics: list[dict]) -> dict:
        return build_allocation_handoff(self.overview, topics, [])

    def test_classifies_state_readings_without_action_semantics(self) -> None:
        handoff = self._build(
            [
                topic(
                    "CANDIDATE.SH",
                    approaching_start=True,
                    market_chart=chart(close=98, ma60=100),
                ),
                topic(
                    "SCALE.SH",
                    trend_active=True,
                    all_stages_passed=True,
                ),
                topic(
                    "STARTER.SH",
                    initial_active=True,
                ),
                topic("HOLD.SH", trend_extension=True),
                topic(
                    "PROTECT.SH",
                    trend_active=True,
                    market_chart=chart(ma60=90, profit_protection=True),
                ),
                topic(
                    "EXIT.SH",
                    initial_active=True,
                    market_chart=chart(close=89, ma60=90),
                ),
                topic(
                    "STALE.SH",
                    initial_active=True,
                    stale_component=True,
                ),
                topic("OBSERVE.SH"),
            ]
        )
        by_code = {item["code"]: item for item in handoff["targets"]}

        expected_reading = {
            "CANDIDATE.SH": ["POSITION_WINDOW_MET"],
            "SCALE.SH": ["ABOVE_MA250_STATE", "THREE_GROUPS_MET"],
            "STARTER.SH": ["ABOVE_MA60_STATE", "MA60_MA250_SEPARATION_MET"],
            "HOLD.SH": ["RELATIVE_EXCESS_MET"],
            "PROTECT.SH": ["TREND_CONFIRMED_ACTIVE", "TWO_DAYS_BELOW_MA20"],
            "EXIT.SH": ["CLOSE_BELOW_MA60"],
            "STALE.SH": ["ENTRY_BLOCKED_STALE_COMPONENTS", "STALE_COMPONENTS_PRESENT"],
            "OBSERVE.SH": ["NO_MA_SIGNAL"],
        }
        for code, codes in expected_reading.items():
            self.assertEqual(by_code[code]["reasonCodes"], codes)
            self.assertEqual(len(by_code[code]["reasons"]), len(codes))

        # 中性化：不再输出 action / 单位 / 指令 / 优先级 / 资金接口语义。
        for item in handoff["targets"]:
            self.assertNotIn("action", item)
            self.assertNotIn("targetAllocationUnits", item)
            self.assertNotIn("allocationInstruction", item)
            self.assertNotIn("positionSignal", item)
            self.assertNotIn("entryPriorityRank", item)
            self.assertNotIn("capitalInterface", item["signal"])

        self.assertTrue(by_code["CANDIDATE.SH"]["stateInputs"]["ma60CrossUpEmerged"])
        self.assertEqual(by_code["CANDIDATE.SH"]["maStateCode"], "above_ma60")
        self.assertFalse(by_code["STALE.SH"]["guards"]["entryDataFresh"])
        self.assertEqual(by_code["STALE.SH"]["reasonCodes"][-1], "STALE_COMPONENTS_PRESENT")
        self.assertTrue(by_code["SCALE.SH"]["guards"]["longCycleHistoryReady"])
        self.assertTrue(by_code["SCALE.SH"]["guards"]["weightFresh"])
        self.assertEqual(by_code["SCALE.SH"]["guards"]["weightAgeCalendarDays"], 4)
        self.assertEqual(handoff["meta"]["schemaVersion"], "2.0")
        self.assertFalse(handoff["meta"]["strategyExecutesOrders"])
        self.assertFalse(handoff["meta"]["positionSizingProvided"])
        self.assertFalse(handoff["meta"]["fixedCnyAmountProvided"])
        self.assertEqual(validate_allocation_handoff(handoff, self.codes, "20260804"), [])

    def test_ma250_cross_without_all_three_stages_stays_unconfirmed(self) -> None:
        handoff = self._build(
            [
                topic(
                    "CANDIDATE.SH",
                    approaching_start=True,
                    market_chart=chart(close=98, ma60=100),
                ),
                topic(
                    "SCALE.SH",
                    trend_active=True,
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

        self.assertEqual(scale["reasonCodes"], ["NO_MA_SIGNAL"])
        self.assertFalse(scale["guards"]["threeGroupsMet"])

    def test_rows_sort_by_objective_ma_state_then_target_order(self) -> None:
        codes_used = {"SCALE.SH", "HOLD.SH", "OBSERVE.SH"}
        overview = {
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
                    "maStateCode": "below_ma20",
                }
                for order, code in enumerate(sorted(codes_used), start=1)
            ],
        }
        handoff = build_allocation_handoff(
            overview,
            [
                topic("OBSERVE.SH"),
                topic(
                    "SCALE.SH",
                    trend_active=True,
                    all_stages_passed=True,
                ),
                topic("HOLD.SH", trend_extension=True),
            ],
            [],
        )
        codes = [item["code"] for item in handoff["targets"]]

        # above_ma250 在前，below_ma20 在后；同档内按 targetOrder。
        self.assertLess(
            codes.index("SCALE.SH"),
            codes.index("HOLD.SH"),
        )
        self.assertLess(
            codes.index("HOLD.SH"),
            codes.index("OBSERVE.SH"),
        )
        self.assertEqual(
            validate_allocation_handoff(handoff, codes_used, "20260804"), []
        )

    def test_history_and_weight_guards_surface_as_reading_blockers(self) -> None:
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
                    "maStateCode": "above_ma60",
                }
            ],
        }
        guarded_topic = topic(
            code,
            approaching_start=True,
            market_chart=chart(close=98, ma60=100),
            history_ready=False,
            weight_date="20260101",
        )
        handoff = build_allocation_handoff(overview, [guarded_topic], [])
        guarded = handoff["targets"][0]

        self.assertEqual(guarded["maStateCode"], "above_ma60")
        self.assertFalse(guarded["guards"]["entryGuardPassed"])
        self.assertFalse(guarded["guards"]["longCycleHistoryReady"])
        self.assertFalse(guarded["guards"]["weightFresh"])
        self.assertIn("ENTRY_BLOCKED_INSUFFICIENT_HISTORY", guarded["reasonCodes"])
        self.assertIn("ENTRY_BLOCKED_STALE_WEIGHTS", guarded["reasonCodes"])
        self.assertEqual(validate_allocation_handoff(handoff, {code}, "20260804"), [])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import unittest
from pathlib import Path


SANDBOX_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SANDBOX_DIR))

from update_signal_followup import build_signal_followup, validate_signal_followup


def topic(code: str, three_groups_met: bool, rows: int = 1) -> dict:
    """构造一个观察层 topic。

    观察层不再输出 label；触发条件由 structure / breakout / leader
    三组读数是否全部达到门槛决定（update_signal_followup._three_groups_met）。
    """
    chart = [
        {
            "date": f"202607{day:02d}",
            "themeNormalized": 100 + day,
            "benchmarkNormalized": 100 + day / 2,
        }
        for day in range(1, rows + 1)
    ]
    return {
        "target": {"code": code, "name": code},
        "stages": [
            {"id": stage_id, "passed": three_groups_met}
            for stage_id in ("structure", "breakout", "leader")
        ],
        "chart": chart,
    }


class SignalFollowupTest(unittest.TestCase):
    def test_records_transition_and_completes_only_available_horizons(self) -> None:
        code = "TEST.SH"
        first_overview = {"targets": [{"code": code, "latestDate": "20260701"}]}
        first = build_signal_followup(
            first_overview,
            [topic(code, True, 1)],
            [],
        )
        self.assertEqual(len(first["events"]), 1)
        self.assertEqual(first["events"][0]["signalCondition"], "three_groups_met")
        self.assertEqual(first["events"][0]["horizons"]["5"]["status"], "pending")

        later_overview = {"targets": [{"code": code, "latestDate": "20260721"}]}
        later = build_signal_followup(
            later_overview,
            [topic(code, False, 21)],
            [],
            first,
        )
        event = later["events"][0]
        self.assertEqual(event["horizons"]["5"]["endDate"], "20260706")
        self.assertEqual(event["horizons"]["20"]["endDate"], "20260721")
        self.assertIn("maxAdverseTargetReturnPct", event["horizons"]["20"])
        self.assertIn("averageExcessReturnPct", later["summary"]["20"])
        self.assertEqual(event["horizons"]["60"]["status"], "pending")
        self.assertEqual(validate_signal_followup(later, {code}, "20260721"), [])

    def test_does_not_duplicate_continuing_signal(self) -> None:
        code = "TEST.SH"
        overview = {"targets": [{"code": code, "latestDate": "20260701"}]}
        first = build_signal_followup(overview, [topic(code, True)], [])
        second_overview = {"targets": [{"code": code, "latestDate": "20260702"}]}
        second = build_signal_followup(
            second_overview,
            [topic(code, True, 2)],
            [],
            first,
        )
        self.assertEqual(len(second["events"]), 1)

    def test_rejects_date_rollback(self) -> None:
        code = "TEST.SH"
        overview = {"targets": [{"code": code, "latestDate": "20260701"}]}
        previous = {
            "meta": {"asOf": "20260702"},
            "latestStates": {code: "not_met"},
            "events": [],
        }
        with self.assertRaisesRegex(ValueError, "cannot move backwards"):
            build_signal_followup(overview, [topic(code, False)], [], previous)


if __name__ == "__main__":
    unittest.main()

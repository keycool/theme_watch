from __future__ import annotations

import sys
import unittest
from pathlib import Path


SANDBOX_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SANDBOX_DIR))

from update_signal_followup import build_signal_followup, validate_signal_followup


def topic(code: str, label: str, rows: int = 1) -> dict:
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
        "summary": {"label": label},
        "chart": chart,
    }


class SignalFollowupTest(unittest.TestCase):
    def test_records_transition_and_completes_only_available_horizons(self) -> None:
        code = "TEST.SH"
        first_overview = {"targets": [{"code": code, "latestDate": "20260701"}]}
        first = build_signal_followup(
            first_overview,
            [topic(code, "启动确认", 1)],
            [],
        )
        self.assertEqual(len(first["events"]), 1)
        self.assertEqual(first["events"][0]["horizons"]["5"]["status"], "pending")

        later_overview = {"targets": [{"code": code, "latestDate": "20260721"}]}
        later = build_signal_followup(
            later_overview,
            [topic(code, "趋势延续", 21)],
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

    def test_does_not_duplicate_continuing_startup_label(self) -> None:
        code = "TEST.SH"
        overview = {"targets": [{"code": code, "latestDate": "20260701"}]}
        first = build_signal_followup(overview, [topic(code, "启动确认")], [])
        second_overview = {"targets": [{"code": code, "latestDate": "20260702"}]}
        second = build_signal_followup(
            second_overview,
            [topic(code, "启动确认", 2)],
            [],
            first,
        )
        self.assertEqual(len(second["events"]), 1)

    def test_rejects_date_rollback(self) -> None:
        code = "TEST.SH"
        overview = {"targets": [{"code": code, "latestDate": "20260701"}]}
        previous = {
            "meta": {"asOf": "20260702"},
            "latestLabels": {code: "观察中"},
            "events": [],
        }
        with self.assertRaisesRegex(ValueError, "cannot move backwards"):
            build_signal_followup(overview, [topic(code, "观察中")], [], previous)


if __name__ == "__main__":
    unittest.main()

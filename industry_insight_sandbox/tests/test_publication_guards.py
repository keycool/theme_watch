from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SANDBOX_DIR = REPOSITORY_ROOT / "industry_insight_sandbox"
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(SANDBOX_DIR))

from guard_production_date import (
    extract_latest_date,
    validate_publication_date,
)
from run_etf_constituent_workflow import _validate_topic_freshness


def valid_topic() -> dict:
    return {
        "meta": {"latestDate": "20260724"},
        "target": {"code": "TEST.CSI"},
        "summary": {
            "label": "观察中",
            "activeCount": 1,
            "aboveMa60Count": 1,
            "aboveMa250Count": 0,
            "strictLeaderConfirmed": False,
        },
        "components": [
            {
                "code": "600001.SH",
                "latestDate": "20260724",
                "dataFresh": True,
                "pct1d": 6.0,
                "ret5d": 2.0,
                "aboveMa60": True,
                "aboveMa250": False,
            },
            {
                "code": "600002.SH",
                "latestDate": "20260723",
                "dataFresh": False,
                "pct1d": 9.9,
                "ret5d": 8.0,
                "aboveMa60": False,
                "aboveMa250": False,
            },
        ],
        "limitEvents": [
            {
                "code": "600002.SH",
                "weightRank": 1,
                "dataFresh": False,
                "qualified": False,
            }
        ],
        "stages": [
            {
                "id": "leader",
                "items": [{"title": "核心群体转强", "passed": True}],
            }
        ],
    }


class ProductionDateGuardTest(unittest.TestCase):
    def test_extracts_single_overview_date(self) -> None:
        overview = {
            "targets": [
                {"latestDate": "20260724"},
                {"latestDate": "20260724"},
            ]
        }

        self.assertEqual(extract_latest_date(overview), "20260724")

    def test_blocks_implicit_rollback(self) -> None:
        with self.assertRaisesRegex(ValueError, "rollback is blocked"):
            validate_publication_date(
                candidate_date="20260723",
                live_date="20260724",
                allow_rollback=False,
                confirmation="",
            )

    def test_requires_exact_human_confirmation_for_rollback(self) -> None:
        with self.assertRaisesRegex(ValueError, "confirmation"):
            validate_publication_date(
                candidate_date="20260723",
                live_date="20260724",
                allow_rollback=True,
                confirmation="yes",
            )

    def test_allows_explicit_confirmed_rollback(self) -> None:
        validate_publication_date(
            candidate_date="20260723",
            live_date="20260724",
            allow_rollback=True,
            confirmation="ROLLBACK 20260723",
        )

    def test_allows_same_or_newer_date_without_rollback_switch(self) -> None:
        validate_publication_date(
            candidate_date="20260724",
            live_date="20260724",
            allow_rollback=False,
            confirmation="",
        )


class TopicFreshnessValidationTest(unittest.TestCase):
    def test_accepts_stale_component_when_excluded_from_signals(self) -> None:
        self.assertEqual(_validate_topic_freshness(valid_topic()), [])

    def test_missing_freshness_fields_fail_validation(self) -> None:
        topic = valid_topic()
        del topic["components"][0]["latestDate"]
        del topic["components"][1]["dataFresh"]

        issues = _validate_topic_freshness(topic)

        self.assertTrue(any("latestDate is missing" in issue for issue in issues))
        self.assertTrue(any("dataFresh is missing" in issue for issue in issues))

    def test_component_date_after_topic_as_of_fails_validation(self) -> None:
        topic = valid_topic()
        topic["components"][0]["latestDate"] = "20260725"

        issues = _validate_topic_freshness(topic)

        self.assertTrue(any("later than topic as_of" in issue for issue in issues))

    def test_stale_component_cannot_create_startup_confirmation(self) -> None:
        topic = valid_topic()
        topic["summary"]["label"] = "启动确认"
        topic["summary"]["strictLeaderConfirmed"] = True
        topic["limitEvents"][0]["qualified"] = True
        topic["limitEvents"][0]["dataFresh"] = False

        issues = _validate_topic_freshness(topic)

        self.assertTrue(any("stale component qualifies as leader" in issue for issue in issues))
        self.assertTrue(any("startup confirmation lacks" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()

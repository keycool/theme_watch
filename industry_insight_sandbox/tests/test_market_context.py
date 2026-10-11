from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SANDBOX_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SANDBOX_DIR))

from build_market_context import (  # noqa: E402
    DECLINE_THRESHOLD_PCT,
    REGIME_MARKET_WIDE,
    REGIME_NONE,
    REGIME_SINGLE_NAME,
    build_context,
    classify,
    ret5_pct,
)


def chart(values: list[float]) -> list[dict]:
    return [{"close": value} for value in values]


class MarketContextTest(unittest.TestCase):
    def test_ret5_uses_six_closes(self) -> None:
        # 100 -> 95 是 5 个交易日后的收益 = -5%
        self.assertAlmostEqual(ret5_pct(chart([100, 101, 102, 99, 97, 95])), -5.0)

    def test_ret5_needs_six_points(self) -> None:
        self.assertIsNone(ret5_pct(chart([100, 101, 102, 99, 97])))

    def test_ret5_ignores_missing_closes(self) -> None:
        rows: list[dict] = [{"close": 100}, {"close": None}, {"close": 102}]
        self.assertIsNone(ret5_pct(rows + [{"close": 99}, {"close": 97}, {"close": 95}]))

    def test_market_wide_when_cross_section_also_falls(self) -> None:
        self.assertEqual(classify(-5.0, -4.0), REGIME_MARKET_WIDE)

    def test_single_name_when_only_the_target_falls(self) -> None:
        self.assertEqual(classify(-5.0, 1.0), REGIME_SINGLE_NAME)

    def test_none_above_threshold_or_missing(self) -> None:
        self.assertEqual(classify(-1.0, -4.0), REGIME_NONE)
        self.assertEqual(classify(None, -4.0), REGIME_NONE)
        self.assertEqual(classify(-5.0, None), REGIME_NONE)

    def test_threshold_boundary_is_inclusive(self) -> None:
        self.assertEqual(classify(DECLINE_THRESHOLD_PCT, -4.0), REGIME_MARKET_WIDE)

    def test_context_carries_cross_section_and_as_of(self) -> None:
        topics = [
            {"target": {"code": "A.SH"}, "chart": chart([100] * 5 + [90])},
            {"target": {"code": "B.SH"}, "chart": chart([100] * 5 + [101])},
            {"target": {"code": "C.SH"}, "chart": chart([100] * 5 + [102])},
        ]
        contexts = build_context(topics, "20260813")
        # 横截面中位数 = 101/100-1 = +1% -> 没普跌；A 单独跌 10%
        self.assertEqual(contexts["A.SH"]["declineRegime"], REGIME_SINGLE_NAME)
        self.assertEqual(contexts["B.SH"]["declineRegime"], REGIME_NONE)
        self.assertAlmostEqual(contexts["A.SH"]["marketRet5MedianPct"], 1.0)
        self.assertEqual(contexts["A.SH"]["contextAsOf"], "20260813")
        self.assertEqual(contexts["A.SH"]["sampleCount"], 3)


class MarketContextArtifactTest(unittest.TestCase):
    def test_published_context_matches_contract(self) -> None:
        path = SANDBOX_DIR / "data" / "market_context.json"
        if not path.exists():
            self.skipTest("market_context.json 尚未生成")
        payload = json.loads(path.read_text(encoding="utf-8"))
        meta = payload["meta"]
        self.assertEqual(meta["schemaVersion"], "1.0")
        self.assertFalse(meta["decisionUse"])
        self.assertEqual(meta["sampleCount"], 23)
        for context in payload["targets"].values():
            self.assertIn(
                context["declineRegime"],
                {REGIME_MARKET_WIDE, REGIME_SINGLE_NAME, REGIME_NONE},
            )
            self.assertEqual(context["contextAsOf"], meta["asOf"])
            self.assertEqual(context["declineThresholdPct"], DECLINE_THRESHOLD_PCT)

    def test_every_topic_carries_context(self) -> None:
        topics = json.loads(
            (SANDBOX_DIR / "data" / "all_topics.json").read_text(encoding="utf-8")
        )
        payload_path = SANDBOX_DIR / "data" / "market_context.json"
        if not payload_path.exists():
            self.skipTest("market_context.json 尚未生成")
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        for topic in topics:
            code = str(topic["target"]["code"])
            self.assertEqual(
                topic["summary"]["observation"]["context"], payload["targets"][code]
            )


if __name__ == "__main__":
    unittest.main()

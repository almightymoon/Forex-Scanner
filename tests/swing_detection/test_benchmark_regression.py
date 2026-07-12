"""Benchmark regression tests against committed label files."""

import json
import unittest
from datetime import datetime
from pathlib import Path

from shared.types.models import Timeframe

from swing_engine import SwingEngine, get_config
from swing_engine.evaluation import SwingBenchmarkEvaluator
from swing_engine.models import BenchmarkLabel, SwingDirection, SwingScope, SwingTier
from tests.swing_detection.fixtures import trend_candles

LABELS_DIR = Path(__file__).resolve().parents[2] / "benchmarks" / "labels"


def _load_labels(path: Path) -> list[BenchmarkLabel]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        BenchmarkLabel(
            pivot_index=item["pivot_index"],
            timestamp=datetime.fromisoformat(item["timestamp"]),
            price=item["price"],
            direction=SwingDirection(item["direction"]),
            tier=SwingTier(item.get("tier", "MAJOR")),
            scope=SwingScope(item.get("scope", "EXTERNAL")),
        )
        for item in data.get("swings", [])
    ]


class TestBenchmarkRegression(unittest.TestCase):
    def test_regression_labels_file_exists(self):
        path = LABELS_DIR / "EURUSD_H1.regression.json"
        self.assertTrue(path.exists(), "Run label generation or commit regression labels")

    def test_v1_1_0_matches_regression_baseline(self):
        path = LABELS_DIR / "EURUSD_H1.regression.json"
        if not path.exists():
            self.skipTest("regression labels not present")
        labels = _load_labels(path)
        bars = trend_candles(120)
        result = SwingEngine(get_config(Timeframe.H1, version="1.1.0"), version="1.1.0").detect(
            bars, symbol="EURUSD", timeframe=Timeframe.H1,
        )
        report = SwingBenchmarkEvaluator(get_config(Timeframe.H1, version="1.1.0")).evaluate(
            result.confirmed_swings, labels, "EURUSD", engine_version="1.1.0",
        )
        self.assertGreaterEqual(report.f1_score, 0.95)
        self.assertEqual(report.false_positives, 0)
        self.assertEqual(report.false_negatives, 0)

    def test_v1_0_0_still_supported(self):
        bars = trend_candles(80)
        result = SwingEngine(version="1.0.0").detect(bars)
        self.assertEqual(result.version, "1.0.0")
        self.assertGreater(len(result.swings), 0)


if __name__ == "__main__":
    unittest.main()

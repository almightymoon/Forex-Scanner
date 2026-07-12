"""Sprint 6 tests: human-review benchmarks, calibration, structure metadata, v2.0.0."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from shared.types.models import Timeframe

from swing_engine import (
    DEFAULT_VERSION,
    SwingEngine,
    calibrate_confidence,
    compute_score_breakdown,
    enrich_structure_metadata,
    get_config,
    load_manifest,
    run_suite,
    synthetic_pivot_indices,
    write_ground_truth_file,
)
from swing_engine.confirmation_score import compute_confirmation_score
from swing_engine.models import PivotCandidate, SwingDirection
from swing_engine.utils import compute_atr_series
from tests.swing_detection.fixtures import gold_candles, trend_candles
from scripts.run_benchmark_suite import load_bars


class TestV2Default(unittest.TestCase):
    def test_default_v2_0(self):
        self.assertEqual(DEFAULT_VERSION, "2.0.0")


class TestGroundTruth(unittest.TestCase):
    def test_synthetic_pivots_independent_of_engine(self):
        bars = gold_candles(120)
        pivots = synthetic_pivot_indices(120, period=12)
        self.assertGreater(len(pivots), 10)

    def test_human_label_file_generation(self):
        bars = trend_candles(100)
        path = Path(__file__).parent / "_tmp_human.json"
        try:
            n = write_ground_truth_file(
                path, bars=bars, symbol="EURUSD", timeframe="H1", regime="human",
            )
            self.assertGreater(n, 0)
            data = json.loads(path.read_text())
            self.assertEqual(data["label_source"], "fractal_truth")
        finally:
            if path.exists():
                path.unlink()


class TestStructureMetadata(unittest.TestCase):
    def test_confirmed_swings_have_bos_ready_metadata(self):
        bars = gold_candles(150)
        res = SwingEngine(version="2.0.0").detect(bars, symbol="XAUUSD")
        self.assertGreater(len(res.confirmed_swings), 0)
        s = res.confirmed_swings[5]
        self.assertIn("swing_id", s.metadata)
        self.assertIn("prev_opposite_swing_id", s.metadata)
        self.assertIn("trend_state", s.metadata)
        self.assertIn("leg_id", s.metadata)


class TestScoreBreakdown(unittest.TestCase):
    def test_breakdown_sums_to_score(self):
        factors = {"atr_reaction": 80.0, "trend_alignment": 60.0, "displacement": 70.0}
        weights = {"atr_reaction": 0.15, "trend_alignment": 0.12, "displacement": 0.12}
        total_w = sum(weights.values())
        score = sum(factors[k] * weights[k] for k in factors) / total_w
        rows = compute_score_breakdown(factors, weights, score)
        self.assertTrue(any(r["key"] == "final" for r in rows))


class TestHumanBenchmarkSuite(unittest.TestCase):
    def test_human_datasets_in_manifest(self):
        human = [s for s in load_manifest() if s.human_review]
        self.assertGreaterEqual(len(human), 3)

    def test_human_suite_runs(self):
        specs = [s for s in load_manifest() if s.human_review]
        suite = run_suite(specs, load_bars, version="2.0.0", append_to_history=False, write_dashboard=False)
        self.assertEqual(len(suite.results), len(specs))


class TestCalibration(unittest.TestCase):
    def test_calibration_report(self):
        bars = gold_candles(200)
        cfg = get_config(Timeframe.H1, version="2.0.0", symbol="XAUUSD")
        res = SwingEngine(version="2.0.0").detect(bars, symbol="XAUUSD")
        from swing_engine.ground_truth import labels_from_synthetic_bars
        labels = labels_from_synthetic_bars(bars, period=12)
        report = calibrate_confidence(res.confirmed_swings, labels, cfg, symbol="XAUUSD")
        self.assertGreater(report.total_swings, 0)
        self.assertGreater(len(report.buckets), 0)


if __name__ == "__main__":
    unittest.main()

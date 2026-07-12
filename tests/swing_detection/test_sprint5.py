"""Sprint 5 tests: score-gated confirmation, benchmark datasets, suite runner."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from shared.types.models import Timeframe

from swing_engine import DEFAULT_VERSION, SwingEngine, get_config, load_manifest, run_suite
from swing_engine.confirmation_score import compute_confirmation_score
from swing_engine.explain import build_swing_explanation
from swing_engine.models import PivotCandidate, SwingDirection
from swing_engine.utils import compute_atr_series
from tests.swing_detection.fixtures import gold_candles, gold_range_candles, trend_candles

# Reuse benchmark bar loader from suite script
from scripts.run_benchmark_suite import load_bars


class TestSprint5Version(unittest.TestCase):
    def test_default_v2_0(self):
        self.assertEqual(DEFAULT_VERSION, "2.0.0")
        self.assertEqual(SwingEngine().version, "2.0.0")


class TestConfirmationScore(unittest.TestCase):
    def test_score_gated_metadata_on_confirmed_swings(self):
        bars = trend_candles(150)
        res = SwingEngine(version="1.4.0").detect(bars)
        self.assertGreater(len(res.confirmed_swings), 0)
        for s in res.confirmed_swings:
            self.assertIn("confirmation_score", s.metadata)
            self.assertGreaterEqual(float(s.metadata["confirmation_score"]), 70.0)
            self.assertIn("confirmation_checks", s.metadata)

    def test_explain_includes_confirmation_audit(self):
        bars = trend_candles(120)
        cfg = get_config(Timeframe.H1, version="1.4.0")
        res = SwingEngine(version="1.4.0").detect(bars)
        swing = res.confirmed_swings[0]
        expl = build_swing_explanation(swing, cfg)
        self.assertTrue(any("Confirmation score" in f for f in expl.factors))
        self.assertTrue(any(f.startswith("✓") for f in expl.factors))

    def test_compute_confirmation_score_returns_audit(self):
        bars = trend_candles(80)
        cfg = get_config(Timeframe.H1, version="1.4.0")
        atr = compute_atr_series(bars, cfg.atr.period)
        pivot = PivotCandidate(
            pivot_index=20,
            pivot_timestamp=bars[20].timestamp,
            price=bars[20].high,
            direction=SwingDirection.HIGH,
            strength=0.8,
        )
        score, factors, checks = compute_confirmation_score(
            pivot, bars, atr, cfg,
            prev_opposite=None,
            prev_same=None,
            conf_index=23,
            delay=3,
        )
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 100.0)
        self.assertIn("hold_quality", factors)
        self.assertGreater(len(checks), 0)


class TestGoldRangeFixture(unittest.TestCase):
    def test_gold_range_produces_swings(self):
        bars = gold_range_candles(200)
        res = SwingEngine(version="1.4.0").detect(bars, symbol="XAUUSD")
        self.assertGreater(len(res.confirmed_swings), 0)


class TestBenchmarkDatasets(unittest.TestCase):
    def test_manifest_has_eleven_datasets(self):
        specs = load_manifest()
        self.assertEqual(len(specs), 11)
        ids = {s.id for s in specs}
        self.assertIn("XAUUSD_H1_range", ids)
        self.assertIn("EURUSD_H1_trend", ids)

    def test_all_label_files_exist_and_nonempty(self):
        labels_dir = Path(__file__).resolve().parents[2] / "benchmarks" / "labels"
        for spec in load_manifest():
            path = labels_dir / spec.labels_file
            self.assertTrue(path.exists(), msg=f"missing {path}")
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertGreater(len(data.get("swings", [])), 0, msg=spec.id)

    def test_suite_passes_all_datasets(self):
        specs = load_manifest()
        suite = run_suite(specs, load_bars, version="2.0.0", append_to_history=False, write_dashboard=False)
        failed = [r for r in suite.results if not r.passed]
        self.assertEqual(
            failed,
            [],
            msg=", ".join(f"{r.spec.id} F1={r.report.f1_score:.3f}" for r in failed),
        )


if __name__ == "__main__":
    unittest.main()

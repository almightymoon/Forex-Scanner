"""Sprint 3 tests: adaptive detection, quality score, explainability,
regression history, and paper-mode validation — including XAUUSD (gold)."""

from __future__ import annotations

import dataclasses
import json
import tempfile
import unittest
from pathlib import Path

from shared.types.models import Timeframe

from swing_engine import (
    DEFAULT_VERSION,
    PaperSwingLog,
    SwingEngine,
    adapt_config,
    append_history,
    compare_against_review,
    compute_market_context,
    get_config,
    load_history,
)
from swing_engine.context import _efficiency_ratio, _session
from swing_engine.models import StructureRegime, VolatilityRegime
from swing_engine.utils import compute_atr_series, pip_size_for_symbol
from tests.swing_detection.fixtures import gold_candles, range_candles, trend_candles


class TestDefaultVersion(unittest.TestCase):
    def test_default_is_v1_2(self):
        self.assertEqual(DEFAULT_VERSION, "1.2.0")
        self.assertEqual(SwingEngine().version, "1.2.0")


class TestGoldPipSizing(unittest.TestCase):
    def test_xauusd_pip_size(self):
        cfg = get_config(Timeframe.H1, version="1.2.0", symbol="XAUUSD")
        self.assertAlmostEqual(pip_size_for_symbol("XAUUSD", cfg), 0.1)

    def test_symbol_override_applied(self):
        cfg = get_config(Timeframe.H1, version="1.2.0", symbol="XAUUSD")
        self.assertEqual(cfg.leg.min_pips, 5.0)
        self.assertEqual(cfg.noise_filter.min_pip_distance, 5.0)

    def test_fx_unaffected(self):
        cfg = get_config(Timeframe.H1, version="1.2.0", symbol="EURUSD")
        self.assertAlmostEqual(pip_size_for_symbol("EURUSD", cfg), 0.0001)


class TestGoldDetection(unittest.TestCase):
    def test_detects_gold_swings(self):
        res = SwingEngine(version="1.2.0").detect(gold_candles(200), symbol="XAUUSD")
        self.assertGreater(len(res.confirmed_swings), 3)

    def test_gold_swings_have_quality(self):
        res = SwingEngine(version="1.2.0").detect(gold_candles(200), symbol="XAUUSD")
        for s in res.confirmed_swings:
            self.assertGreaterEqual(s.quality_score, 0.0)
            self.assertLessEqual(s.quality_score, 100.0)


class TestMarketContext(unittest.TestCase):
    def test_context_populated(self):
        res = SwingEngine(version="1.2.0").detect(trend_candles(150))
        ctx = res.artifacts.market_context
        self.assertIsNotNone(ctx)
        self.assertIn(ctx.volatility_regime, list(VolatilityRegime))
        self.assertIn(ctx.structure_regime, list(StructureRegime))

    def test_trend_is_trending(self):
        bars = trend_candles(150, step=0.004)
        atr = compute_atr_series(bars, 14)
        ctx = compute_market_context(bars, atr, get_config(Timeframe.H1, version="1.2.0"))
        self.assertEqual(ctx.structure_regime, StructureRegime.TRENDING)

    def test_efficiency_ratio_bounds(self):
        bars = trend_candles(60)
        er = _efficiency_ratio(bars, 20)
        self.assertGreaterEqual(er, 0.0)
        self.assertLessEqual(er, 1.0)

    def test_session_classification(self):
        bars = gold_candles(30)
        s = _session(bars[5])  # hour 5 -> Asia
        self.assertIsNotNone(s)


class TestAdaptiveConfig(unittest.TestCase):
    def test_disabled_returns_same(self):
        cfg = get_config(Timeframe.H1, version="1.0.0")
        self.assertFalse(cfg.adaptive.enabled)
        bars = trend_candles(80)
        atr = compute_atr_series(bars, 14)
        ctx = compute_market_context(bars, atr, cfg)
        self.assertIs(adapt_config(cfg, ctx), cfg)

    def test_enabled_scales_thresholds(self):
        cfg = get_config(Timeframe.H1, version="1.2.0")
        self.assertTrue(cfg.adaptive.enabled)
        bars = trend_candles(120, step=0.004)
        atr = compute_atr_series(bars, 14)
        ctx = compute_market_context(bars, atr, cfg)
        adapted = adapt_config(cfg, ctx)
        # thresholds should differ from base after adaptation
        changed = (
            adapted.noise_filter.min_pip_distance != cfg.noise_filter.min_pip_distance
            or adapted.leg.min_atr_multiple != cfg.leg.min_atr_multiple
            or adapted.classification.major_min_atr_multiple != cfg.classification.major_min_atr_multiple
        )
        self.assertTrue(changed)

    def test_adaptation_does_not_mutate_base(self):
        cfg = get_config(Timeframe.H1, version="1.2.0")
        base_pip = cfg.noise_filter.min_pip_distance
        bars = trend_candles(120)
        atr = compute_atr_series(bars, 14)
        ctx = compute_market_context(bars, atr, cfg)
        adapt_config(cfg, ctx)
        self.assertEqual(cfg.noise_filter.min_pip_distance, base_pip)


class TestQualityScore(unittest.TestCase):
    def test_quality_in_range(self):
        res = SwingEngine(version="1.2.0").detect(trend_candles(150))
        for s in res.swings:
            self.assertGreaterEqual(s.quality_score, 0.0)
            self.assertLessEqual(s.quality_score, 100.0)

    def test_quality_factors_present(self):
        res = SwingEngine(version="1.2.0").detect(trend_candles(150))
        s = res.confirmed_swings[0]
        for key in ("confirmation", "displacement", "wick", "atr_normalization",
                    "leg_symmetry", "liquidity_sweep", "trend_alignment"):
            self.assertIn(key, s.quality_factors)


class TestExplainability(unittest.TestCase):
    def test_swing_has_explanation(self):
        res = SwingEngine(version="1.2.0").detect(trend_candles(150))
        s = res.confirmed_swings[0]
        self.assertIsNotNone(s.explanation)
        self.assertEqual(s.explanation.status, "accepted")
        self.assertTrue(s.explanation.summary)
        self.assertGreater(len(s.explanation.factors), 0)
        self.assertIn("quality", s.explanation.stage_scores)

    def test_rejected_candidates_explained_in_timeline(self):
        res = SwingEngine(version="1.2.0").detect(range_candles(150))
        rejected = [e for e in res.artifacts.decision_timeline if e.get("status") == "rejected"]
        # At least some rejections should carry an explanation summary
        if rejected:
            self.assertTrue(any("explanation" in e for e in rejected))

    def test_to_dict_serializable(self):
        res = SwingEngine(version="1.2.0").detect(trend_candles(120))
        d = res.swings[0].to_dict()
        self.assertIn("quality_score", d)
        self.assertIn("explanation", d)
        json.dumps(res.to_dict())  # must not raise


class TestRegressionHistory(unittest.TestCase):
    def test_append_and_load(self):
        from swing_engine import SwingBenchmarkEvaluator
        from swing_engine.models import BenchmarkLabel

        res = SwingEngine(version="1.2.0").detect(gold_candles(200), symbol="XAUUSD")
        gt = [BenchmarkLabel(s.pivot_index, s.timestamp, s.price, s.direction, s.tier, s.scope)
              for s in res.confirmed_swings]
        report = SwingBenchmarkEvaluator(get_config(Timeframe.H1, version="1.2.0", symbol="XAUUSD")).evaluate(
            res.confirmed_swings, gt, "XAUUSD",
            engine_version="1.2.0", benchmark_version="self", regime="trend",
        )
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "hist.jsonl"
            append_history(report, path)
            append_history(report, path)
            entries = load_history(path)
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0]["symbol"], "XAUUSD")
            self.assertEqual(entries[0]["engine_version"], "1.2.0")


class TestPaperValidation(unittest.TestCase):
    def test_record_and_compare(self):
        res = SwingEngine(version="1.2.0").detect(gold_candles(200), symbol="XAUUSD")
        with tempfile.TemporaryDirectory() as td:
            log = PaperSwingLog(Path(td) / "paper.jsonl")
            recorded = log.record(res)
            self.assertGreater(len(recorded), 0)
            # dedupe: recording again adds nothing
            self.assertEqual(len(log.record(res)), 0)

            reviewed = [
                {"pivot_index": s.pivot_index, "price": s.price, "direction": s.direction.value}
                for s in res.confirmed_swings
            ]
            result = compare_against_review(log.load(), reviewed, price_tolerance=0.5, index_tolerance=2)
            self.assertEqual(result.recall, 1.0)
            self.assertEqual(result.precision, 1.0)


if __name__ == "__main__":
    unittest.main()

"""Sprint 4 tests: lifecycle, replay, MTF, rules, optimizer."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from shared.types.models import Timeframe

from swing_engine import (
    DEFAULT_VERSION,
    ParamGrid,
    SwingEngine,
    SwingReplayEngine,
    SwingLifecycleState,
    build_lifecycle,
    detect_mtf_hierarchy,
    run_optimization,
)
from swing_engine.models import BenchmarkLabel, SwingDirection, SwingScope, SwingTier
from tests.swing_detection.fixtures import gold_candles, trend_candles


class TestSprint4Version(unittest.TestCase):
    def test_default_v1_3(self):
        self.assertEqual(DEFAULT_VERSION, "1.3.0")


class TestLifecycle(unittest.TestCase):
    def test_lifecycle_tracks_populated(self):
        res = SwingEngine(version="1.3.0").detect(trend_candles(150))
        self.assertGreater(len(res.artifacts.lifecycle_tracks), 0)
        self.assertIn("repainting_rate", res.artifacts.repainting_stats)

    def test_swing_has_lifecycle_state(self):
        res = SwingEngine(version="1.3.0").detect(trend_candles(150))
        for s in res.swings:
            self.assertIsNotNone(s.lifecycle_state)

    def test_confirmed_swings_are_confirmed_state(self):
        res = SwingEngine(version="1.3.0").detect(trend_candles(150))
        for s in res.confirmed_swings:
            self.assertIn(s.lifecycle_state, (
                SwingLifecycleState.CONFIRMED,
                SwingLifecycleState.WAITING_CONFIRMATION,
            ))


class TestRuleChecks(unittest.TestCase):
    def test_rule_checks_on_swings(self):
        res = SwingEngine(version="1.3.0").detect(gold_candles(200), symbol="XAUUSD")
        s = res.confirmed_swings[0]
        self.assertGreater(len(s.rule_checks), 0)
        self.assertTrue(any(r.rule_id == "confirmation" for r in s.rule_checks))


class TestReplay(unittest.TestCase):
    def test_replay_builds_frames(self):
        bars = gold_candles(120)
        session = SwingReplayEngine(version="1.3.0").build_session(
            bars, symbol="XAUUSD", min_bars=40, step=10,
        )
        self.assertGreater(session.total_frames, 0)
        last = session.frames[-1]
        self.assertGreater(last.swing_count, 0)

    def test_next_frame(self):
        bars = trend_candles(80)
        engine = SwingReplayEngine(version="1.3.0")
        r1 = engine.next_frame(bars, bar_index=50)
        r2 = engine.next_frame(bars, bar_index=79)
        self.assertLessEqual(len(r1.swings), len(r2.swings))


class TestMTF(unittest.TestCase):
    def test_mtf_hierarchy_gold(self):
        from tests.swing_detection.fixtures import swing_candles

        bars_h1 = gold_candles(200)
        bars_h4 = swing_candles(
            80, base=2350, wave=12, trend=0.8, period=12, symbol="XAUUSD", timeframe=Timeframe.H4,
        )
        result = detect_mtf_hierarchy(
            {"H4": bars_h4, "H1": bars_h1},
            symbol="XAUUSD",
            version="1.3.0",
            hierarchy=["H4", "H1"],
        )
        self.assertIn("H1", result.swings_by_timeframe)
        h1_swings = result.swings_by_timeframe["H1"]
        self.assertGreater(len(h1_swings), 0)
        self.assertIsNotNone(h1_swings[0].mtf_context)
        self.assertEqual(h1_swings[0].mtf_context.parent_timeframe, "H4")


class TestOptimizer(unittest.TestCase):
    def test_optimizer_runs_small_grid(self):
        bars = trend_candles(120)
        res = SwingEngine(version="1.3.0").detect(bars)
        labels = [
            BenchmarkLabel(s.pivot_index, s.timestamp, s.price, s.direction, s.tier, s.scope)
            for s in res.confirmed_swings[:5]
        ]
        grid = ParamGrid(
            pivot_left_lookback=(3,),
            confirmation_delay_bars=(2,),
            leg_min_atr_multiple=(0.35,),
            quality_min_acceptable=(50.0,),
            major_min_atr_multiple=(1.2,),
        )
        results = run_optimization(bars, labels, symbol="EURUSD", timeframe=Timeframe.H1, grid=grid)
        self.assertEqual(len(results), 1)
        self.assertGreater(results[0].rank_score, 0)


if __name__ == "__main__":
    unittest.main()

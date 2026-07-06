"""Tests for configuration and ATR utilities."""

import unittest

from shared.types.models import Timeframe

from scanner.swing_detection.utils import (
    compute_atr_series,
    get_swing_detection_config,
    pip_size_for_symbol,
    pips_to_price,
)
from tests.swing_detection.fixtures import swing_candles


class TestSwingDetectionConfig(unittest.TestCase):
    def test_loads_from_yaml(self):
        cfg = get_swing_detection_config()
        self.assertEqual(cfg.atr.period, 14)
        self.assertGreater(cfg.pivot.left_lookback, 0)

    def test_timeframe_override(self):
        m1 = get_swing_detection_config(Timeframe.M1)
        d1 = get_swing_detection_config(Timeframe.D1)
        self.assertLessEqual(m1.pivot.left_lookback, d1.pivot.left_lookback)

    def test_pip_size_jpy(self):
        cfg = get_swing_detection_config()
        self.assertEqual(pip_size_for_symbol("USDJPY", cfg), 0.01)
        self.assertEqual(pip_size_for_symbol("EURUSD", cfg), 0.0001)

    def test_pips_to_price(self):
        cfg = get_swing_detection_config()
        self.assertAlmostEqual(pips_to_price(10, "EURUSD", cfg), 0.001)


class TestAtrUtils(unittest.TestCase):
    def test_atr_series_length(self):
        cs = swing_candles(50)
        atrs = compute_atr_series(cs, 14)
        self.assertEqual(len(atrs), len(cs))

    def test_atr_positive(self):
        cs = swing_candles(30)
        atrs = compute_atr_series(cs, 14)
        self.assertTrue(all(a > 0 for a in atrs))


if __name__ == "__main__":
    unittest.main()

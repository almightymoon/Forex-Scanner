"""Unified scan path: one confirmed-swing pass for SMC + features + decision."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from shared.types.models import Timeframe, TrendDirection
from swing_engine.models import DetectedSwing, SwingDirection, SwingScope, SwingTier

from services.quant_engine.detection.smc import SMCEngine
from services.quant_engine.decision.engine import DecisionEngine
from services.quant_engine.features.extractor import FeatureExtractor
from services.quant_engine.market_structure.detector import analyze_structure
from services.quant_engine.swings.boundary import SCAN_SWING_VERSION, obtain_confirmed_swings
from tests.helpers import candles, indicators


SMC_PATH = Path(__file__).resolve().parents[2] / "services/quant_engine/detection/smc.py"
DECISION_PATH = (
    Path(__file__).resolve().parents[2] / "services/quant_engine/decision/engine.py"
)


def _wavy(n: int = 80) -> list[float]:
    return [1.10 + (i % 6) * 0.002 + i * 0.0002 for i in range(n)]


def _ts(index: int) -> datetime:
    return datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(hours=index)


def _swing(pivot: int, direction: SwingDirection, price: float, confirmation: int) -> DetectedSwing:
    return DetectedSwing(
        timestamp=_ts(pivot),
        price=price,
        direction=direction,
        tier=SwingTier.MAJOR,
        scope=SwingScope.EXTERNAL,
        pivot_index=pivot,
        confirmed=True,
        confirmation_index=confirmation,
        confirmation_delay=max(0, confirmation - pivot),
        score=70.0,
    )


def test_scan_swing_version_decision_is_2_3_0():
    assert SCAN_SWING_VERSION == "2.3.0"


def test_smc_does_not_call_legacy_analyze_market_structure():
    source = SMC_PATH.read_text(encoding="utf-8")
    assert "analyze_market_structure(" not in source
    assert "analyze_structure" in source
    assert "obtain_confirmed_swings" in source


def test_smc_bos_from_v1_snapshot_with_injected_swings():
    # Build a short synthetic prefix with an explicit bullish BOS.
    from shared.types.models import Candle

    cs = []
    for i in range(25):
        cs.append(
            Candle(
                symbol="SYN",
                timeframe=Timeframe.H1,
                timestamp=_ts(i),
                open=10.0,
                high=12.0,
                low=8.0,
                close=10.0,
                volume=100.0,
            )
        )
    cs[3] = Candle(
        symbol="SYN",
        timeframe=Timeframe.H1,
        timestamp=_ts(3),
        open=10.0,
        high=11.0,
        low=8.0,
        close=10.5,
        volume=100.0,
    )
    swings = [_swing(1, SwingDirection.HIGH, 10.0, 2)]
    snap = analyze_structure(cs, swings)
    patterns = SMCEngine().detect_all(
        cs,
        "SYN",
        Timeframe.H1,
        confirmed_swings=swings,
        structure_snapshot=snap,
    )
    bos = [p for p in patterns if p.pattern_type == "bos"]
    assert bos
    assert bos[0].metadata.get("structure_source") == "market_structure_v1"
    assert bos[0].metadata.get("event_id")


def test_smc_reuses_injected_swings_without_second_obtain():
    from tests.swing_detection.fixtures import gold_candles

    cs = gold_candles(120, wave=10.0, trend=0.04, period=16, seed=3)
    swings = obtain_confirmed_swings(cs, version=SCAN_SWING_VERSION)
    assert swings, "v2.3 gold fixture should yield confirmed swings"
    snap = analyze_structure(cs, swings)
    with patch(
        "services.quant_engine.detection.smc.obtain_confirmed_swings"
    ) as obtain_mock:
        SMCEngine().detect_all(
            cs,
            cs[0].symbol,
            Timeframe.H1,
            confirmed_swings=swings,
            structure_snapshot=snap,
        )
        assert not obtain_mock.called


def test_decision_engine_passes_features_into_trend_analyze():
    source = DECISION_PATH.read_text(encoding="utf-8")
    assert "self.trend_engine.analyze(candles, indicators, features)" in source
    assert "run_from_structure_snapshot" in source


def test_decision_evaluate_reuses_snapshot_and_swings():
    from tests.swing_detection.fixtures import gold_candles

    cs = gold_candles(120, wave=10.0, trend=0.04, period=16, seed=3)
    ind = indicators(
        symbol=cs[0].symbol,
        ema_20=2350.0,
        ema_50=2340.0,
        ema_200=2320.0,
        atr_14=5.0,
        adx_14=28,
    )
    swings = obtain_confirmed_swings(cs, version=SCAN_SWING_VERSION)
    snap = analyze_structure(cs, swings)
    patterns = SMCEngine().detect_all(
        cs,
        cs[0].symbol,
        Timeframe.H1,
        confirmed_swings=swings,
        structure_snapshot=snap,
    )
    with (
        patch(
            "services.quant_engine.decision.engine.build_scan_structure"
        ) as build_mock,
        patch(
            "services.quant_engine.decision.engine.analyze_structure",
            wraps=analyze_structure,
        ) as analyze_mock,
    ):
        signal = DecisionEngine().evaluate(
            symbol=cs[0].symbol,
            timeframe=Timeframe.H1,
            candles=cs,
            indicators=ind,
            smc_patterns=patterns,
            confirmed_swings=swings,
            structure_snapshot=snap,
        )
        assert not build_mock.called
        # Snapshot supplied → DecisionEngine should not re-run analyze_structure.
        assert not analyze_mock.called
        assert signal.market_features is not None
        assert signal.trend in (
            TrendDirection.BULLISH,
            TrendDirection.BEARISH,
            TrendDirection.RANGING,
        )


def test_feature_extractor_accepts_shared_snapshot():
    from tests.swing_detection.fixtures import gold_candles

    cs = gold_candles(120, wave=10.0, trend=0.04, period=16, seed=3)
    ind = indicators(symbol=cs[0].symbol, ema_20=2350.0, ema_50=2340.0, atr_14=5.0)
    swings = obtain_confirmed_swings(cs, version=SCAN_SWING_VERSION)
    snap = analyze_structure(cs, swings)
    with patch(
        "services.quant_engine.features.extractor.analyze_structure",
        wraps=analyze_structure,
    ) as analyze_mock:
        features = FeatureExtractor().extract(
            cs,
            ind,
            [],
            confirmed_swings=swings,
            structure_snapshot=snap,
        )
        assert not analyze_mock.called
        assert features.structure_snapshot is snap
        assert features.structure_metadata.get("swing_version") == SCAN_SWING_VERSION
        assert features.structure_regime

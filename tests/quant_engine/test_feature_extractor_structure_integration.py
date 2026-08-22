"""FeatureExtractor integration with Market Structure Engine v1."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from tests.helpers import indicators as make_indicators
from shared.types.models import (
    Candle,
    SMCPattern,
    SignalDirection,
    Timeframe,
    TrendDirection,
)
from swing_engine.models import DetectedSwing, SwingDirection, SwingScope, SwingTier

from services.quant_engine.features.extractor import FEATURE_SWING_VERSION, FeatureExtractor


ROOT = Path(__file__).resolve().parents[2]
EXTRACTOR_PATH = ROOT / "services/quant_engine/features/extractor.py"
DETECTOR_PATH = ROOT / "services/quant_engine/market_structure/detector.py"


def _ts(index: int) -> datetime:
    return datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(hours=index)


def _candle(index: int, *, high: float, low: float, close: float) -> Candle:
    return Candle(
        symbol="SYN",
        timeframe=Timeframe.H1,
        timestamp=_ts(index),
        open=(high + low) / 2.0,
        high=high,
        low=low,
        close=close,
        volume=100.0,
    )


def _swing(
    pivot: int,
    direction: SwingDirection,
    price: float,
    *,
    confirmation: int,
    tier: SwingTier = SwingTier.MAJOR,
    scope: SwingScope = SwingScope.EXTERNAL,
) -> DetectedSwing:
    return DetectedSwing(
        timestamp=_ts(pivot),
        price=price,
        direction=direction,
        tier=tier,
        scope=scope,
        pivot_index=pivot,
        confirmed=True,
        confirmation_index=confirmation,
        confirmation_delay=max(0, confirmation - pivot),
        score=65.0,
    )


def _indicators():
    return make_indicators(
        ema_20=10.2,
        ema_50=9.8,
        ema_200=9.0,
        atr_14=0.5,
        adx_14=28.0,
        rsi_14=55.0,
    )


def test_feature_extractor_uses_new_detector_with_injected_swings():
    candles = [_candle(i, high=12, low=8, close=10) for i in range(10)]
    candles[3] = _candle(3, high=11, low=8, close=10.5)
    swings = [_swing(1, SwingDirection.HIGH, 10.0, confirmation=2)]
    features = FeatureExtractor().extract(
        candles,
        _indicators(),
        [],
        confirmed_swings=swings,
    )
    assert features.structure_snapshot is not None
    assert features.external_bias is TrendDirection.BULLISH
    assert features.last_structure_event == "bos"
    assert features.structure_metadata.get("detector") == "market_structure_v1"
    assert features.structure_metadata.get("swing_version") == FEATURE_SWING_VERSION


def test_feature_extractor_does_not_call_legacy_structure():
    candles = [_candle(i, high=12, low=8, close=10) for i in range(10)]
    candles[3] = _candle(3, high=11, low=8, close=10.5)
    swings = [_swing(1, SwingDirection.HIGH, 10.0, confirmation=2)]
    with (
        patch(
            "services.quant_engine.features.extractor.analyze_structure",
            wraps=__import__(
                "services.quant_engine.market_structure.detector",
                fromlist=["analyze_structure"],
            ).analyze_structure,
        ) as analyze_mock,
        patch(
            "services.quant_engine.swing_analysis.analyze_market_structure"
        ) as legacy_structure,
        patch(
            "services.quant_engine.swing_analysis.build_zigzag_swings"
        ) as legacy_zigzag,
        patch(
            "services.quant_engine.swing_analysis.analyze_trend_context"
        ) as legacy_trend,
    ):
        FeatureExtractor().extract(
            candles, _indicators(), [], confirmed_swings=swings
        )
        assert analyze_mock.called
        assert not legacy_structure.called
        assert not legacy_zigzag.called
        assert not legacy_trend.called


def test_confirmed_swings_passed_through_unchanged():
    candles = [_candle(i, high=12, low=8, close=10) for i in range(10)]
    swings = [_swing(1, SwingDirection.HIGH, 10.0, confirmation=2)]
    original_id = id(swings[0])
    features = FeatureExtractor().extract(
        candles, _indicators(), [], confirmed_swings=swings
    )
    assert features.swing_count == 1
    assert id(swings[0]) == original_id
    assert swings[0].price == 10.0
    assert swings[0].confirmation_index == 2


def test_external_and_pending_and_internal_bias_fields():
    candles = [_candle(i, high=20, low=5, close=12) for i in range(20)]
    candles[3] = _candle(3, high=11, low=8, close=10.5)
    candles[10] = _candle(10, high=12, low=7, close=8.5)
    swings = [
        _swing(1, SwingDirection.HIGH, 10.0, confirmation=2),
        _swing(6, SwingDirection.LOW, 9.0, confirmation=8),
        _swing(
            12,
            SwingDirection.HIGH,
            11.0,
            confirmation=14,
            tier=SwingTier.MINOR,
            scope=SwingScope.INTERNAL,
        ),
    ]
    features = FeatureExtractor().extract(
        candles, _indicators(), [], confirmed_swings=swings[:2], as_of_index=10
    )
    assert features.external_bias is TrendDirection.BULLISH
    assert features.pending_external_bias is TrendDirection.BEARISH
    assert features.internal_bias is TrendDirection.RANGING
    assert features.last_structure_event == "choch"
    assert "choch" in (features.latest_bos_choch or {}).get("event_type", "").lower() or (
        features.latest_bos_choch or {}
    ).get("event_type") == "CHOCH"


def test_bos_and_choch_metadata_propagate():
    candles = [_candle(i, high=12, low=8, close=10) for i in range(8)]
    candles[3] = _candle(3, high=11, low=8, close=10.5)
    swings = [_swing(1, SwingDirection.HIGH, 10.0, confirmation=2)]
    features = FeatureExtractor().extract(
        candles, _indicators(), [], confirmed_swings=swings
    )
    assert features.structure_event_ids
    assert features.latest_structure_event_id == features.structure_event_ids[-1]
    assert features.latest_bos_choch is not None
    assert features.bos_kind == "external"


def test_empty_swings_safe():
    candles = [_candle(i, high=12, low=8, close=10) for i in range(5)]
    features = FeatureExtractor().extract(
        candles, _indicators(), [], confirmed_swings=[]
    )
    assert features.structure_snapshot is not None
    assert features.external_bias is TrendDirection.RANGING
    assert features.swing_count == 0
    assert features.structure_event_ids == []


def test_prefix_reproducibility_through_feature_layer():
    candles = [_candle(i, high=20, low=5, close=12) for i in range(25)]
    candles[3] = _candle(3, high=11, low=8, close=10.5)
    candles[12] = _candle(12, high=13, low=9, close=12.5)
    swings = [
        _swing(1, SwingDirection.HIGH, 10.0, confirmation=2),
        _swing(6, SwingDirection.HIGH, 12.0, confirmation=8),
    ]
    n = 12
    full = FeatureExtractor().extract(
        candles, _indicators(), [], confirmed_swings=swings, as_of_index=20
    )
    prefix = FeatureExtractor().extract(
        candles[: n + 1],
        _indicators(),
        [],
        confirmed_swings=[s for s in swings if s.confirmation_index <= n],
        as_of_index=n,
    )
    full_events = [
        e.to_dict()
        for e in full.structure_snapshot.events
        if e.break_index <= n
    ]
    prefix_events = [e.to_dict() for e in prefix.structure_snapshot.events]
    assert full_events == prefix_events


def test_no_lookahead_in_feature_as_of():
    candles = [_candle(i, high=12, low=8, close=9.5) for i in range(10)]
    candles[5] = _candle(5, high=11, low=8, close=10.5)
    swings = [_swing(1, SwingDirection.HIGH, 10.0, confirmation=2)]
    early = FeatureExtractor().extract(
        candles, _indicators(), [], confirmed_swings=swings, as_of_index=4
    )
    assert early.structure_event_ids == []
    later = FeatureExtractor().extract(
        candles, _indicators(), [], confirmed_swings=swings, as_of_index=5
    )
    assert later.structure_event_ids
    assert later.structure_snapshot is not None
    assert all(e.break_index <= 5 for e in later.structure_snapshot.events)


def test_extractor_source_avoids_legacy_structure_helpers():
    source = EXTRACTOR_PATH.read_text(encoding="utf-8")
    assert "analyze_structure" in source
    assert "build_zigzag_swings" not in source
    assert "analyze_trend_context" not in source
    # No callable / import use of the legacy structure analyzer.
    assert "analyze_market_structure(" not in source
    assert "analyze_market_structure," not in source


def test_detector_source_has_no_swing_engine_or_get_config():
    source = DETECTOR_PATH.read_text(encoding="utf-8")
    assert "SwingEngine" not in source
    assert "get_config" not in source


def test_ob_fvg_still_extracted():
    candles = [_candle(i, high=12, low=8, close=10) for i in range(20)]
    patterns = [
        SMCPattern(
            pattern_type="order_block",
            direction=SignalDirection.BUY,
            price_low=9.5,
            price_high=10.0,
            metadata={"index": 15, "impulse_ratio": 2.0},
        ),
        SMCPattern(
            pattern_type="fvg",
            direction=SignalDirection.BUY,
            price_low=10.1,
            price_high=10.3,
            metadata={"gap_size": 0.2},
        ),
    ]
    features = FeatureExtractor().extract(
        candles, _indicators(), patterns, confirmed_swings=[]
    )
    assert features.ob_count == 1
    assert features.fvg_count == 1
    assert features.best_ob is not None
    assert features.best_fvg is not None


def test_legacy_public_imports_still_work():
    from services.quant_engine.market_structure import (
        MarketStructureEngine,
        StructureQuality,
        analyze_structure,
        score_structure_event,
        structure_snapshot_to_features,
    )

    assert callable(analyze_structure)
    assert callable(structure_snapshot_to_features)
    assert MarketStructureEngine is not None
    assert StructureQuality is not None
    assert callable(score_structure_event)

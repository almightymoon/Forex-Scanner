"""Structure-proximity boosts for OB/FVG quality."""

from __future__ import annotations

from datetime import datetime

from shared.types.models import SMCPattern, SignalDirection, TrendDirection
from swing_engine.models import SwingScope

from services.quant_engine.features.types import MarketFeatures
from services.quant_engine.fvg.engine import FairValueGapEngine
from services.quant_engine.market_structure.models import (
    StructureEvent,
    StructureEventType,
    StructureSnapshot,
)
from services.quant_engine.market_structure.proximity import assess_structure_proximity
from services.quant_engine.order_blocks.engine import OrderBlockEngine


def _event(
    *,
    event_type: StructureEventType = StructureEventType.BOS,
    direction: TrendDirection = TrendDirection.BULLISH,
    break_index: int = 50,
    level_price: float = 100.0,
    event_id: str = "evt-1",
) -> StructureEvent:
    return StructureEvent(
        event_id=event_id,
        event_type=event_type,
        direction=direction,
        scope=SwingScope.EXTERNAL,
        level_swing_id="sw1",
        level_pivot_index=max(0, break_index - 5),
        level_price=level_price,
        level_available_index=max(0, break_index - 2),
        break_index=break_index,
        break_timestamp=datetime(2024, 6, 1, 12, 0, 0),
        break_close=level_price,
        prior_bias=TrendDirection.RANGING,
        resulting_bias=direction,
        pending_bias=TrendDirection.RANGING,
        is_continuation=event_type is StructureEventType.BOS,
    )


def _snapshot(events: tuple[StructureEvent, ...]) -> StructureSnapshot:
    return StructureSnapshot(
        as_of_index=100,
        external_bias=TrendDirection.BULLISH,
        pending_external_bias=TrendDirection.RANGING,
        internal_bias=TrendDirection.BULLISH,
        pending_internal_bias=TrendDirection.RANGING,
        swing_relations=(),
        events=events,
        latest_external_high=110.0,
        latest_external_low=90.0,
        latest_internal_high=105.0,
        latest_internal_low=95.0,
    )


def test_proximity_boosts_near_agreeing_bos():
    snapshot = _snapshot((_event(break_index=50),))
    near = assess_structure_proximity(
        SMCPattern(
            pattern_type="order_block",
            direction=SignalDirection.BUY,
            price_low=99.0,
            price_high=101.0,
            strength=70,
            metadata={"index": 52},
        ),
        snapshot,
        candle_count=80,
        atr=1.0,
    )
    assert near.agrees_with_event is True
    assert near.boost >= 1

    far = assess_structure_proximity(
        SMCPattern(
            pattern_type="order_block",
            direction=SignalDirection.BUY,
            price_low=99.0,
            price_high=101.0,
            strength=70,
            metadata={"index": 90},
        ),
        snapshot,
        candle_count=100,
    )
    assert far.boost == 0


def test_ob_engine_applies_proximity_boost():
    snapshot = _snapshot((_event(break_index=10),))
    pattern = SMCPattern(
        pattern_type="order_block",
        direction=SignalDirection.BUY,
        price_low=99.5,
        price_high=100.5,
        strength=70,
        metadata={"index": 11, "impulse_ratio": 2.0},
    )
    features = MarketFeatures(structure_snapshot=snapshot, atr=1.0)
    out = OrderBlockEngine().run([pattern], candles=[], features=features)
    assert out.metadata["qualities"]
    assert out.metadata["qualities"][0].get("structure_proximity", {}).get("boost", 0) >= 1


def test_fvg_engine_applies_proximity_boost():
    snapshot = _snapshot(
        (
            _event(
                event_id="choch-1",
                event_type=StructureEventType.CHOCH,
                direction=TrendDirection.BEARISH,
                break_index=20,
                level_price=200.0,
            ),
        )
    )
    pattern = SMCPattern(
        pattern_type="fvg",
        direction=SignalDirection.SELL,
        price_low=199.0,
        price_high=201.0,
        strength=65,
        metadata={"index": 21, "gap_size": 2.0},
    )
    features = MarketFeatures(structure_snapshot=snapshot, atr=1.0)
    out = FairValueGapEngine().run([pattern], candles=[], features=features)
    assert out.metadata["gaps"]
    assert out.metadata["gaps"][0].get("structure_proximity", {}).get("boost", 0) >= 1

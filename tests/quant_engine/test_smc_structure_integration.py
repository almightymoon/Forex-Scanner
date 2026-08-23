"""SMC consumes StructureSnapshot — no independent swing sequence for BOS/CHoCH."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from shared.types.models import Candle, Timeframe, TrendDirection
from swing_engine.models import DetectedSwing, SwingDirection, SwingScope, SwingTier

from services.quant_engine.detection.smc import SMCEngine
from services.quant_engine.market_structure.detector import analyze_structure
from services.quant_engine.market_structure.models import StructureEventType
from services.quant_engine.swings.boundary import SCAN_SWING_VERSION, obtain_confirmed_swings
from tests.swing_detection.fixtures import gold_candles

SMC_PATH = Path(__file__).resolve().parents[2] / "services/quant_engine/detection/smc.py"


def _ts(i: int) -> datetime:
    return datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i)


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
        score=80.0,
    )


def test_smc_source_has_no_legacy_structure_discovery():
    source = SMC_PATH.read_text(encoding="utf-8")
    assert "analyze_market_structure(" not in source
    assert "build_zigzag_swings" not in source
    assert "find_swings" not in source
    assert "classify_bos" not in source
    assert "analyze_structure" in source


def test_smc_bos_choch_equal_snapshot_events():
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
        cs, "SYN", Timeframe.H1, confirmed_swings=swings, structure_snapshot=snap
    )
    structure_patterns = [p for p in patterns if p.pattern_type in {"bos", "choch"}]
    assert structure_patterns
    for p in structure_patterns:
        assert p.metadata.get("structure_source") == "market_structure_v1"
        assert p.metadata.get("event_id") in {e.event_id for e in snap.events}


def test_smc_cannot_invent_bos_from_independent_swings_when_snapshot_empty_events():
    """With an injected snapshot that has no events, SMC must not emit snapshot BOS."""
    cs = gold_candles(80, seed=2)
    swings = obtain_confirmed_swings(cs, version=SCAN_SWING_VERSION)
    snap = analyze_structure(cs, [])  # empty swings → typically no events
    patterns = SMCEngine().detect_all(
        cs,
        "XAUUSD",
        Timeframe.H1,
        confirmed_swings=swings,
        structure_snapshot=snap,
    )
    snap_bos = [
        p
        for p in patterns
        if p.pattern_type in {"bos", "choch"}
        and p.metadata.get("structure_source") == "market_structure_v1"
    ]
    assert snap.events == () or all(
        p.metadata.get("event_id") in {e.event_id for e in snap.events} for p in snap_bos
    )
    if not snap.events:
        assert not snap_bos


def test_smc_reuses_injected_swings_without_obtain():
    cs = gold_candles(100, seed=4)
    swings = obtain_confirmed_swings(cs, version=SCAN_SWING_VERSION)
    snap = analyze_structure(cs, swings)
    with patch("services.quant_engine.detection.smc.obtain_confirmed_swings") as m:
        SMCEngine().detect_all(
            cs, "XAUUSD", Timeframe.H1, confirmed_swings=swings, structure_snapshot=snap
        )
        assert not m.called

"""Smart Money Concepts detection engine.

BOS / CHoCH consume Market Structure Engine v1. FVG and Order Block patterns
are ranked views over canonical lifecycle zone sets (no last-N truncation of
history in the detectors). Liquidity sweeps / equal highs-lows are emitted
only from Liquidity Engine v1 snapshots (no parallel SMC liquidity detector).
"""

from __future__ import annotations

from services.quant_engine.fvg.lifecycle import detect_fvg_zones
from services.quant_engine.fvg.models import FVGZoneSet
from services.quant_engine.fvg.patterns import patterns_from_fvg_zones
from services.quant_engine.market_structure.detector import analyze_structure
from services.quant_engine.market_structure.integration import build_market_structure_state
from services.quant_engine.market_structure.models import (
    StructureEventType,
    StructureSnapshot,
)
from services.quant_engine.order_blocks.lifecycle import detect_order_block_zones
from services.quant_engine.order_blocks.models import OrderBlockZoneSet
from services.quant_engine.order_blocks.patterns import patterns_from_ob_zones
from services.quant_engine.swing_analysis import MarketStructureState
from services.quant_engine.swings.boundary import (
    SCAN_SWING_VERSION,
    obtain_confirmed_swings,
)
from shared.types.models import Candle, SMCPattern, SignalDirection, Timeframe, TrendDirection
from swing_engine.models import DetectedSwing, SwingScope


class SMCEngine:
    """Detects institutional price action patterns."""

    def detect_all(
        self,
        candles: list[Candle],
        symbol: str,
        timeframe: Timeframe,
        *,
        confirmed_swings: list[DetectedSwing] | None = None,
        structure_snapshot: StructureSnapshot | None = None,
        liquidity_snapshot=None,
        fvg_zones: FVGZoneSet | None = None,
        ob_zones: OrderBlockZoneSet | None = None,
        ranking_htf_trend: TrendDirection | None = None,
        ranking_htf_tf: str | None = None,
    ) -> list[SMCPattern]:
        if len(candles) < 20:
            return []

        swings = (
            list(confirmed_swings)
            if confirmed_swings is not None
            else obtain_confirmed_swings(candles, version=SCAN_SWING_VERSION)
        )
        if confirmed_swings is None:
            # Standalone SMC entry — not the live DataLoader path.
            import logging

            logging.getLogger("fxnav.smc").warning(
                "SMCEngine.detect_all obtained swings internally; "
                "live scan must pass confirmed_swings + structure_snapshot"
            )
        if structure_snapshot is not None:
            snapshot = structure_snapshot
        else:
            snapshot = analyze_structure(candles, swings)
            if confirmed_swings is not None:
                import logging

                logging.getLogger("fxnav.smc").debug(
                    "SMCEngine rebuilt StructureSnapshot from provided swings"
                )

        structure = build_market_structure_state(snapshot, swings)
        patterns: list[SMCPattern] = []
        patterns.extend(self._detect_bos_choch(snapshot, structure))

        price = float(candles[-1].close)
        atr = 0.0
        if len(candles) >= 2:
            atr = sum(c.high - c.low for c in candles[-14:]) / min(14, len(candles))

        # Liquidity Engine v1 is the sole detector for sweeps / equal levels.
        from services.quant_engine.liquidity.analyzer import analyze_liquidity
        from services.quant_engine.liquidity.patterns import patterns_from_liquidity_snapshot

        liq = liquidity_snapshot
        if liq is None:
            liq = analyze_liquidity(
                candles,
                snapshot=snapshot,
                patterns=[],
                atr=atr,
                external_bias=snapshot.external_bias,
                symbol=symbol,
                timeframe=timeframe,
            )
        if liq.atr and liq.atr > 0:
            atr = float(liq.atr)

        fvg_set = fvg_zones
        if fvg_set is None:
            fvg_set = detect_fvg_zones(candles, symbol=symbol, timeframe=timeframe)
        ob_set = ob_zones
        if ob_set is None:
            ob_set = detect_order_block_zones(candles, symbol=symbol, timeframe=timeframe)

        trend = ranking_htf_trend
        patterns.extend(
            patterns_from_ob_zones(
                ob_set,
                price=price,
                atr=atr,
                structure=snapshot,
                liquidity=liq,
                trend=trend,
                htf_trend_tf=ranking_htf_tf,
            )
        )
        patterns.extend(
            patterns_from_fvg_zones(
                fvg_set,
                price=price,
                atr=atr,
                structure=snapshot,
                liquidity=liq,
                trend=trend,
                htf_trend_tf=ranking_htf_tf,
            )
        )
        patterns.extend(patterns_from_liquidity_snapshot(liq))
        return patterns

    def _detect_bos_choch(
        self,
        snapshot: StructureSnapshot,
        structure: MarketStructureState,
    ) -> list[SMCPattern]:
        """Emit BOS/CHoCH patterns from causal v1 structure events."""

        patterns: list[SMCPattern] = []
        strength = int(structure.swing_strength_avg) if structure.swing_strength_avg else 70

        # Prefer recent events (external first, then internal).
        events = sorted(
            snapshot.events,
            key=lambda e: (e.break_index, 0 if e.scope is SwingScope.EXTERNAL else 1),
        )
        for event in events[-6:]:
            direction = (
                SignalDirection.BUY
                if event.direction is TrendDirection.BULLISH
                else SignalDirection.SELL
            )
            pattern_type = (
                "bos"
                if event.event_type is StructureEventType.BOS
                else "choch"
            )
            bos_kind = (
                "external" if event.scope is SwingScope.EXTERNAL else "internal"
            )
            meta = {
                "event_id": event.event_id,
                "bos_kind": bos_kind,
                "break_index": event.break_index,
                "level_pivot_index": event.level_pivot_index,
                "continuation": event.is_continuation,
                "structure_source": "market_structure_v1",
                "scope": event.scope.value,
            }
            if event.direction is TrendDirection.BULLISH:
                patterns.append(
                    SMCPattern(
                        pattern_type=pattern_type,
                        direction=direction,
                        price_high=event.level_price,
                        strength=strength if pattern_type == "bos" else max(55, strength - 10),
                        metadata=meta,
                    )
                )
            else:
                patterns.append(
                    SMCPattern(
                        pattern_type=pattern_type,
                        direction=direction,
                        price_low=event.level_price,
                        strength=strength if pattern_type == "bos" else max(55, strength - 10),
                        metadata=meta,
                    )
                )

        if structure.last_event and not patterns:
            direction = (
                SignalDirection.BUY
                if structure.event_direction == "buy"
                else SignalDirection.SELL
            )
            patterns.append(
                SMCPattern(
                    pattern_type=structure.last_event,
                    direction=direction,
                    strength=strength,
                    metadata={
                        "bos_kind": structure.bos_kind,
                        "continuation": structure.continuation,
                        "structure_source": "market_structure_v1",
                    },
                )
            )

        return patterns


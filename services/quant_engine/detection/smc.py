"""Smart Money Concepts detection engine.

BOS / CHoCH / swing-based liquidity and equal levels consume Market Structure
Engine v1 over confirmed swings. Order blocks and FVGs remain candle-local.
"""

from __future__ import annotations

from services.quant_engine.market_structure.detector import analyze_structure
from services.quant_engine.market_structure.integration import build_market_structure_state
from services.quant_engine.market_structure.models import (
    StructureEventType,
    StructureSnapshot,
)
from services.quant_engine.swing_analysis import MarketStructureState, build_zigzag_swings
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
    ) -> list[SMCPattern]:
        if len(candles) < 20:
            return []

        swings = (
            list(confirmed_swings)
            if confirmed_swings is not None
            else obtain_confirmed_swings(candles, version=SCAN_SWING_VERSION)
        )
        if structure_snapshot is not None:
            snapshot = structure_snapshot
        else:
            snapshot = analyze_structure(candles, swings)

        structure = build_market_structure_state(snapshot, swings)
        patterns: list[SMCPattern] = []
        patterns.extend(self._detect_bos_choch(snapshot, structure))
        patterns.extend(self._detect_order_blocks(candles))
        patterns.extend(self._detect_fvg(candles))
        patterns.extend(self._detect_liquidity_sweeps(candles, structure))
        patterns.extend(self._detect_equal_levels(candles, structure))
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

    def _detect_order_blocks(self, candles: list[Candle]) -> list[SMCPattern]:
        patterns: list[SMCPattern] = []
        for i in range(3, len(candles) - 1):
            c = candles[i]
            next_c = candles[i + 1]
            body = abs(c.close - c.open)
            next_body = abs(next_c.close - next_c.open)

            if c.close < c.open and next_c.close > next_c.open and next_body > body * 1.5:
                patterns.append(
                    SMCPattern(
                        pattern_type="order_block",
                        direction=SignalDirection.BUY,
                        price_low=c.low,
                        price_high=c.high,
                        strength=75,
                        metadata={"index": i, "impulse_ratio": next_body / max(body, 1e-8)},
                    )
                )
            elif c.close > c.open and next_c.close < next_c.open and next_body > body * 1.5:
                patterns.append(
                    SMCPattern(
                        pattern_type="order_block",
                        direction=SignalDirection.SELL,
                        price_low=c.low,
                        price_high=c.high,
                        strength=75,
                        metadata={"index": i, "impulse_ratio": next_body / max(body, 1e-8)},
                    )
                )

        return patterns[-3:]

    def _detect_fvg(self, candles: list[Candle]) -> list[SMCPattern]:
        patterns: list[SMCPattern] = []
        for i in range(2, len(candles)):
            c1, c2, c3 = candles[i - 2], candles[i - 1], candles[i]
            if c1.high < c3.low:
                patterns.append(
                    SMCPattern(
                        pattern_type="fvg",
                        direction=SignalDirection.BUY,
                        price_low=c1.high,
                        price_high=c3.low,
                        strength=65,
                        metadata={"gap_size": c3.low - c1.high},
                    )
                )
            elif c1.low > c3.high:
                patterns.append(
                    SMCPattern(
                        pattern_type="fvg",
                        direction=SignalDirection.SELL,
                        price_low=c3.high,
                        price_high=c1.low,
                        strength=65,
                        metadata={"gap_size": c1.low - c3.high},
                    )
                )
        return patterns[-3:]

    def _detect_liquidity_sweeps(
        self, candles: list[Candle], structure: MarketStructureState
    ) -> list[SMCPattern]:
        patterns: list[SMCPattern] = []
        if len(candles) < 10:
            return patterns

        last = candles[-1]
        if structure.swing_lows:
            recent_low = structure.swing_lows[-1].price
            if last.low < recent_low and last.close > recent_low:
                patterns.append(
                    SMCPattern(
                        pattern_type="liquidity_sweep",
                        direction=SignalDirection.BUY,
                        price_low=last.low,
                        strength=80,
                        metadata={"swept_level": recent_low, "swing_based": True},
                    )
                )

        if structure.swing_highs:
            recent_high = structure.swing_highs[-1].price
            if last.high > recent_high and last.close < recent_high:
                patterns.append(
                    SMCPattern(
                        pattern_type="liquidity_sweep",
                        direction=SignalDirection.SELL,
                        price_high=last.high,
                        strength=80,
                        metadata={"swept_level": recent_high, "swing_based": True},
                    )
                )

        if not patterns:
            recent_low = min(c.low for c in candles[-10:-1])
            recent_high = max(c.high for c in candles[-10:-1])
            if last.low < recent_low and last.close > recent_low:
                patterns.append(
                    SMCPattern(
                        pattern_type="liquidity_sweep",
                        direction=SignalDirection.BUY,
                        price_low=last.low,
                        strength=70,
                        metadata={"swept_level": recent_low},
                    )
                )
            elif last.high > recent_high and last.close < recent_high:
                patterns.append(
                    SMCPattern(
                        pattern_type="liquidity_sweep",
                        direction=SignalDirection.SELL,
                        price_high=last.high,
                        strength=70,
                        metadata={"swept_level": recent_high},
                    )
                )

        return patterns

    def _detect_equal_levels(
        self, candles: list[Candle], structure: MarketStructureState
    ) -> list[SMCPattern]:
        patterns: list[SMCPattern] = []
        tolerance = 0.0003

        highs = structure.swing_highs[-5:] if structure.swing_highs else []
        for i in range(len(highs)):
            for j in range(i + 1, len(highs)):
                if abs(highs[i].price - highs[j].price) / highs[i].price < tolerance:
                    patterns.append(
                        SMCPattern(
                            pattern_type="equal_highs",
                            direction=SignalDirection.SELL,
                            price_high=highs[i].price,
                            strength=int((highs[i].strength + highs[j].strength) / 2),
                            metadata={"swing_based": True},
                        )
                    )
                    break

        lows = structure.swing_lows[-5:] if structure.swing_lows else []
        for i in range(len(lows)):
            for j in range(i + 1, len(lows)):
                if abs(lows[i].price - lows[j].price) / lows[i].price < tolerance:
                    patterns.append(
                        SMCPattern(
                            pattern_type="equal_lows",
                            direction=SignalDirection.BUY,
                            price_low=lows[i].price,
                            strength=int((lows[i].strength + lows[j].strength) / 2),
                            metadata={"swing_based": True},
                        )
                    )
                    break

        if not patterns:
            patterns.extend(self._legacy_equal_levels(candles))
        return patterns

    def _legacy_equal_levels(self, candles: list[Candle]) -> list[SMCPattern]:
        patterns: list[SMCPattern] = []
        tolerance = 0.0003
        highs = [(i, c.high) for i, c in enumerate(candles[-20:])]
        lows = [(i, c.low) for i, c in enumerate(candles[-20:])]

        for i in range(len(highs)):
            for j in range(i + 1, len(highs)):
                if abs(highs[i][1] - highs[j][1]) / highs[i][1] < tolerance:
                    patterns.append(
                        SMCPattern(
                            pattern_type="equal_highs",
                            direction=SignalDirection.SELL,
                            price_high=highs[i][1],
                            strength=55,
                        )
                    )
                    break

        for i in range(len(lows)):
            for j in range(i + 1, len(lows)):
                if abs(lows[i][1] - lows[j][1]) / lows[i][1] < tolerance:
                    patterns.append(
                        SMCPattern(
                            pattern_type="equal_lows",
                            direction=SignalDirection.BUY,
                            price_low=lows[i][1],
                            strength=55,
                        )
                    )
                    break
        return patterns

    def _find_swing_points(
        self, candles: list[Candle], point_type: str, lookback: int = 3
    ) -> list[tuple[int, float]]:
        """Backward-compatible — delegates to shared zigzag detection."""
        swings = build_zigzag_swings(candles, lookback=lookback)
        filtered = [s for s in swings if s.kind == ("high" if point_type == "high" else "low")]
        return [(s.index, s.price) for s in filtered]

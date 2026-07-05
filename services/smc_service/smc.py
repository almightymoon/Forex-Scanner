"""Smart Money Concepts detection engine."""

from shared.types.models import Candle, SMCPattern, SignalDirection, Timeframe


class SMCEngine:
    """Detects institutional price action patterns."""

    def detect_all(
        self, candles: list[Candle], symbol: str, timeframe: Timeframe
    ) -> list[SMCPattern]:
        if len(candles) < 20:
            return []

        patterns: list[SMCPattern] = []
        patterns.extend(self._detect_bos_choch(candles))
        patterns.extend(self._detect_order_blocks(candles))
        patterns.extend(self._detect_fvg(candles))
        patterns.extend(self._detect_liquidity_sweeps(candles))
        patterns.extend(self._detect_equal_levels(candles))
        return patterns

    def _detect_bos_choch(self, candles: list[Candle]) -> list[SMCPattern]:
        patterns: list[SMCPattern] = []
        swing_highs = self._find_swing_points(candles, "high")
        swing_lows = self._find_swing_points(candles, "low")

        if len(swing_highs) >= 2:
            prev_high = swing_highs[-2]
            curr_high = swing_highs[-1]
            if curr_high[1] > prev_high[1]:
                patterns.append(
                    SMCPattern(
                        pattern_type="bos",
                        direction=SignalDirection.BUY,
                        price_high=curr_high[1],
                        strength=70,
                        metadata={"swing_index": curr_high[0]},
                    )
                )
            elif curr_high[1] < prev_high[1]:
                patterns.append(
                    SMCPattern(
                        pattern_type="choch",
                        direction=SignalDirection.SELL,
                        price_high=curr_high[1],
                        strength=60,
                    )
                )

        if len(swing_lows) >= 2:
            prev_low = swing_lows[-2]
            curr_low = swing_lows[-1]
            if curr_low[1] < prev_low[1]:
                patterns.append(
                    SMCPattern(
                        pattern_type="bos",
                        direction=SignalDirection.SELL,
                        price_low=curr_low[1],
                        strength=70,
                    )
                )
            elif curr_low[1] > prev_low[1]:
                patterns.append(
                    SMCPattern(
                        pattern_type="choch",
                        direction=SignalDirection.BUY,
                        price_low=curr_low[1],
                        strength=60,
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

        return patterns[-3:]  # keep recent only

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

    def _detect_liquidity_sweeps(self, candles: list[Candle]) -> list[SMCPattern]:
        patterns: list[SMCPattern] = []
        if len(candles) < 10:
            return patterns

        recent_low = min(c.low for c in candles[-10:-1])
        recent_high = max(c.high for c in candles[-10:-1])
        last = candles[-1]

        if last.low < recent_low and last.close > recent_low:
            patterns.append(
                SMCPattern(
                    pattern_type="liquidity_sweep",
                    direction=SignalDirection.BUY,
                    price_low=last.low,
                    strength=80,
                    metadata={"swept_level": recent_low},
                )
            )
        elif last.high > recent_high and last.close < recent_high:
            patterns.append(
                SMCPattern(
                    pattern_type="liquidity_sweep",
                    direction=SignalDirection.SELL,
                    price_high=last.high,
                    strength=80,
                    metadata={"swept_level": recent_high},
                )
            )

        return patterns

    def _detect_equal_levels(self, candles: list[Candle]) -> list[SMCPattern]:
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
        swings: list[tuple[int, float]] = []
        for i in range(lookback, len(candles) - lookback):
            if point_type == "high":
                if all(candles[i].high >= candles[i - j].high for j in range(1, lookback + 1)) and all(
                    candles[i].high >= candles[i + j].high for j in range(1, lookback + 1)
                ):
                    swings.append((i, candles[i].high))
            else:
                if all(candles[i].low <= candles[i - j].low for j in range(1, lookback + 1)) and all(
                    candles[i].low <= candles[i + j].low for j in range(1, lookback + 1)
                ):
                    swings.append((i, candles[i].low))
        return swings

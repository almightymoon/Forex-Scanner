"""Bar-by-bar swing replay (Sprint 4).

Steps through candles one at a time so you can watch the engine think —
exactly like TradingView replay for quant debugging.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shared.types.models import Candle, Timeframe

from swing_engine.config import SwingEngineConfig, get_config
from swing_engine.detector import SwingEngine
from swing_engine.models import DetectionResult, SwingLifecycleState, SwingTrackedCandidate


@dataclass
class ReplayFrame:
    """State of the engine after processing bar `bar_index`."""

    bar_index: int
    bar_count: int
    timestamp: str
    swing_count: int
    confirmed_count: int
    waiting_count: int
    rejected_count: int
    new_events: list[dict[str, Any]] = field(default_factory=list)
    snapshot: DetectionResult | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "bar_index": self.bar_index,
            "bar_count": self.bar_count,
            "timestamp": self.timestamp,
            "swing_count": self.swing_count,
            "confirmed_count": self.confirmed_count,
            "waiting_count": self.waiting_count,
            "rejected_count": self.rejected_count,
            "new_events": self.new_events,
        }


@dataclass
class SwingReplaySession:
    """Replay session over a full bar series."""

    symbol: str
    timeframe: Timeframe
    version: str
    frames: list[ReplayFrame] = field(default_factory=list)
    min_bars: int = 30

    @property
    def total_frames(self) -> int:
        return len(self.frames)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "version": self.version,
            "total_frames": self.total_frames,
            "frames": [f.to_dict() for f in self.frames],
        }


class SwingReplayEngine:
    """Build replay frames by re-running detection on growing windows."""

    def __init__(self, version: str = "1.3.0", config: SwingEngineConfig | None = None):
        self._version = version
        self._config = config
        self._engine = SwingEngine(config, version=version)

    def build_session(
        self,
        bars: list[Candle],
        *,
        symbol: str | None = None,
        timeframe: Timeframe | None = None,
        min_bars: int = 30,
        step: int = 1,
        include_snapshots: bool = False,
    ) -> SwingReplaySession:
        if not bars:
            tf = timeframe or Timeframe.H1
            return SwingReplaySession(symbol=symbol or "UNKNOWN", timeframe=tf, version=self._version)

        sym = symbol or bars[0].symbol
        tf = timeframe or bars[0].timeframe
        session = SwingReplaySession(symbol=sym, timeframe=tf, version=self._version, min_bars=min_bars)

        prev_track_states: dict[str, str] = {}

        for end in range(min_bars, len(bars) + 1, step):
            window = bars[:end]
            result = self._engine.detect(window, symbol=sym, timeframe=tf)
            tracks = result.artifacts.lifecycle_tracks
            new_events: list[dict[str, Any]] = []

            for track in tracks:
                prev = prev_track_states.get(track.swing_id)
                cur = track.state.value
                if prev != cur:
                    new_events.append({
                        "swing_id": track.swing_id,
                        "from": prev,
                        "to": cur,
                        "pivot_index": track.pivot_index,
                        "direction": track.direction.value,
                        "bar_index": end - 1,
                    })
                prev_track_states[track.swing_id] = cur

            waiting = sum(1 for t in tracks if t.state == SwingLifecycleState.WAITING_CONFIRMATION)
            rejected = sum(1 for t in tracks if t.state == SwingLifecycleState.REJECTED)

            session.frames.append(ReplayFrame(
                bar_index=end - 1,
                bar_count=end,
                timestamp=window[-1].timestamp.isoformat(),
                swing_count=len(result.swings),
                confirmed_count=len(result.confirmed_swings),
                waiting_count=waiting,
                rejected_count=rejected,
                new_events=new_events,
                snapshot=result if include_snapshots else None,
            ))

        return session

    def next_frame(
        self,
        bars: list[Candle],
        *,
        bar_index: int,
        symbol: str | None = None,
        timeframe: Timeframe | None = None,
    ) -> DetectionResult:
        """Single-step: detect on bars[:bar_index+1]."""
        if bar_index < 0 or bar_index >= len(bars):
            raise IndexError(f"bar_index {bar_index} out of range [0, {len(bars)})")
        sym = symbol or bars[0].symbol
        tf = timeframe or bars[0].timeframe
        return self._engine.detect(bars[: bar_index + 1], symbol=sym, timeframe=tf)

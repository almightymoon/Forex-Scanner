"""
Swing Detection Engine — versioned public API.

    bars → detect_swings() → List[DetectedSwing]
"""

from __future__ import annotations

from typing import Any

from shared.types.models import Candle, Timeframe

from swing_engine.config import SwingEngineConfig, get_config
from swing_engine.models import DetectedSwing, DetectionResult
from swing_engine.versions import DEFAULT_VERSION, get_pipeline, resolve_version


class SwingEngine:
    """Versioned swing detection engine."""

    def __init__(self, config: SwingEngineConfig | None = None, version: str = DEFAULT_VERSION):
        self._config = config
        self._version = resolve_version(version)
        self._detect = get_pipeline(self._version)

    @property
    def version(self) -> str:
        return self._version

    def detect(
        self,
        bars: list[Candle],
        *,
        symbol: str | None = None,
        timeframe: Timeframe | None = None,
        config: SwingEngineConfig | None = None,
    ) -> DetectionResult:
        cfg = config or self._config or get_config(
            timeframe or (bars[0].timeframe if bars else None),
            version=self._version,
        )
        return self._detect(bars, symbol=symbol, timeframe=timeframe, config=cfg)


def detect_swings(
    bars: list[Candle],
    timeframe: Timeframe | None = None,
    version: str = DEFAULT_VERSION,
    **config_overrides: Any,
) -> list[DetectedSwing]:
    tf = timeframe or (bars[0].timeframe if bars else Timeframe.H1)
    cfg = get_config(tf, version=version, **config_overrides) if config_overrides else get_config(tf, version=version)
    return SwingEngine(cfg, version=version).detect(bars, timeframe=tf).swings


# Legacy aliases
SwingDetectionEngine = SwingEngine
SwingDetector = SwingEngine

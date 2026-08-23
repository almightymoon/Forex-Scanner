"""SMC Confluence Engine v1 — models.

Assembles already-computed Structure / Liquidity / FVG / OB / MTF artifacts
into one explainable context. Does not detect swings, BOS, pools, or gaps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

SMC_CONFLUENCE_ENGINE_VERSION = "1.0.0"


class ConfluenceBias(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    MIXED = "MIXED"
    NEUTRAL = "NEUTRAL"
    UNDEFINED = "UNDEFINED"


class ConfluenceStrength(str, Enum):
    WEAK = "WEAK"
    MODERATE = "MODERATE"
    STRONG = "STRONG"
    NONE = "NONE"


@dataclass(frozen=True)
class EvidenceItem:
    side: str  # bullish | bearish | neutral
    category: str  # structure | liquidity | fvg | order_block | mtf
    label: str
    weight: float
    source_timeframe: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "side": self.side,
            "category": self.category,
            "label": self.label,
            "weight": round(self.weight, 3),
            "source_timeframe": self.source_timeframe,
            "metadata": dict(sorted(self.metadata.items())),
        }


@dataclass(frozen=True)
class ConflictItem:
    label: str
    categories: tuple[str, ...]
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "categories": list(self.categories),
            "detail": self.detail,
        }


@dataclass(frozen=True)
class AlgorithmVersions:
    smc_confluence_engine: str = SMC_CONFLUENCE_ENGINE_VERSION
    swing_engine: str = "2.3.0"
    market_structure: str = "1.0.0"
    liquidity_engine: str = "1.0.0"
    fvg_engine: str = "1.0.0"
    order_block_engine: str = "1.0.0"
    mtf_engine: str = "1.0.0"

    def to_dict(self) -> dict[str, str]:
        return {
            "smc_confluence_engine": self.smc_confluence_engine,
            "swing_engine": self.swing_engine,
            "market_structure": self.market_structure,
            "liquidity_engine": self.liquidity_engine,
            "fvg_engine": self.fvg_engine,
            "order_block_engine": self.order_block_engine,
            "mtf_engine": self.mtf_engine,
        }


@dataclass(frozen=True)
class SMCContextSnapshot:
    """Canonical SMC context at one causal point in time."""

    symbol: str
    timeframe: str
    as_of_index: int
    timestamp: str | None

    trend: str
    structure_regime: str
    external_bias: str
    pending_external_bias: str

    last_bos: dict[str, Any] | None
    last_choch: dict[str, Any] | None

    liquidity_context: dict[str, Any]
    fvg_context: dict[str, Any]
    order_block_context: dict[str, Any]
    mtf_context: dict[str, Any]

    bullish_confluences: tuple[EvidenceItem, ...]
    bearish_confluences: tuple[EvidenceItem, ...]
    conflicts: tuple[ConflictItem, ...]

    bullish_score: float
    bearish_score: float
    evidence_strength: float
    dominant_bias: ConfluenceBias
    confluence_strength: ConfluenceStrength
    confidence: float

    explanations: tuple[str, ...]
    setup_confluence: dict[str, Any] | None
    algorithm_versions: AlgorithmVersions

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "as_of_index": self.as_of_index,
            "timestamp": self.timestamp,
            "trend": self.trend,
            "structure_regime": self.structure_regime,
            "external_bias": self.external_bias,
            "pending_external_bias": self.pending_external_bias,
            "last_bos": self.last_bos,
            "last_choch": self.last_choch,
            "liquidity_context": dict(self.liquidity_context),
            "fvg_context": dict(self.fvg_context),
            "order_block_context": dict(self.order_block_context),
            "mtf_context": dict(self.mtf_context),
            "bullish_confluences": [e.to_dict() for e in self.bullish_confluences],
            "bearish_confluences": [e.to_dict() for e in self.bearish_confluences],
            "conflicts": [c.to_dict() for c in self.conflicts],
            "bullish_score": round(self.bullish_score, 3),
            "bearish_score": round(self.bearish_score, 3),
            "evidence_strength": round(self.evidence_strength, 3),
            "dominant_bias": self.dominant_bias.value,
            "confluence_strength": self.confluence_strength.value,
            "confidence": round(self.confidence, 3),
            "explanations": list(self.explanations),
            "setup_confluence": self.setup_confluence,
            "algorithm_versions": self.algorithm_versions.to_dict(),
        }

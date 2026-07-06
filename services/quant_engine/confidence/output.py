"""Standardized output schema for all analysis engines."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EngineOutput:
    name: str
    score: int
    max_score: int
    confidence: float
    direction: str = "NEUTRAL"
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "score": self.score,
            "max_score": self.max_score,
            "confidence": round(self.confidence, 3),
            "direction": self.direction,
            "reasons": self.reasons,
            "metadata": self.metadata,
            "warnings": self.warnings,
        }


def clamp_score(score: int, max_score: int) -> int:
    return max(0, min(score, max_score))


def confidence_from_score(score: int, max_score: int) -> float:
    if max_score <= 0:
        return 0.0
    return round(score / max_score, 3)

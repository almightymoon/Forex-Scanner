"""Validation report — outcome summary for a symbol or global scope."""

from dataclasses import dataclass, field

from .metrics import ValidationMetrics


@dataclass
class ValidationReport:
    scope: str
    metrics: ValidationMetrics
    recent_outcomes: list[dict] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scope": self.scope,
            "metrics": self.metrics.to_dict(),
            "recent_outcomes": self.recent_outcomes,
            "recommendations": self.recommendations,
        }

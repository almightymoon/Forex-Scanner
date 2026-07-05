"""Validation metrics — aggregate prediction vs outcome statistics."""

from dataclasses import dataclass, field


@dataclass
class ValidationMetrics:
    total_signals: int = 0
    closed_signals: int = 0
    wins: int = 0
    losses: int = 0
    breakeven: int = 0
    win_rate: float = 0.0
    avg_score_winners: float = 0.0
    avg_score_losers: float = 0.0
    avg_confidence_winners: float = 0.0
    avg_confidence_losers: float = 0.0
    precision_by_score_band: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "total_signals": self.total_signals,
            "closed_signals": self.closed_signals,
            "wins": self.wins,
            "losses": self.losses,
            "breakeven": self.breakeven,
            "win_rate": round(self.win_rate, 1),
            "avg_score_winners": round(self.avg_score_winners, 1),
            "avg_score_losers": round(self.avg_score_losers, 1),
            "avg_confidence_winners": round(self.avg_confidence_winners, 3),
            "avg_confidence_losers": round(self.avg_confidence_losers, 3),
            "precision_by_score_band": self.precision_by_score_band,
        }

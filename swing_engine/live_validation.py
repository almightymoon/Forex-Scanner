"""Real-world / paper-mode validation (Sprint 3, Priority 5).

After benchmark testing on synthetic/historical data, validate the engine on
unseen live data:

    1. Run the engine in paper mode as bars arrive.
    2. Save every detected swing with timestamps (bar time + wall-clock).
    3. Later compare against human review or benchmark rules.
    4. Measure *live* precision, recall, and detection delay separately from
       historical backtests.

This catches issues caused by real-time confirmation delays or market
conditions that are not obvious in historical testing. It does not implement
detection — it only records and scores :class:`DetectionResult` output.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from swing_engine.models import DetectionResult

DEFAULT_LOG = Path("benchmarks/live/paper_swings.jsonl")


@dataclass
class LoggedSwing:
    detected_at: str
    symbol: str
    timeframe: str
    version: str
    bar_timestamp: str
    pivot_index: int
    price: float
    direction: str
    tier: str
    scope: str
    confirmed: bool
    confirmation_index: int | None
    confirmation_delay: int
    confidence: float
    quality_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "detected_at": self.detected_at,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "version": self.version,
            "bar_timestamp": self.bar_timestamp,
            "pivot_index": self.pivot_index,
            "price": round(self.price, 6),
            "direction": self.direction,
            "tier": self.tier,
            "scope": self.scope,
            "confirmed": self.confirmed,
            "confirmation_index": self.confirmation_index,
            "confirmation_delay": self.confirmation_delay,
            "confidence": round(self.confidence, 4),
            "quality_score": round(self.quality_score, 1),
        }


class PaperSwingLog:
    """Append-only JSONL log of swings detected in paper mode."""

    def __init__(self, path: Path = DEFAULT_LOG):
        self.path = path

    def record(
        self,
        result: DetectionResult,
        *,
        only_confirmed: bool = True,
        dedupe: bool = True,
    ) -> list[LoggedSwing]:
        """Append newly-detected swings. Dedupe by (bar_timestamp, direction)."""
        existing = {(e["bar_timestamp"], e["direction"]) for e in self.load()} if dedupe else set()
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        swings = result.confirmed_swings if only_confirmed else result.swings
        new_entries: list[LoggedSwing] = []
        for s in swings:
            key = (s.timestamp.isoformat(), s.direction.value)
            if dedupe and key in existing:
                continue
            new_entries.append(
                LoggedSwing(
                    detected_at=now,
                    symbol=result.symbol,
                    timeframe=result.timeframe.value,
                    version=result.version,
                    bar_timestamp=s.timestamp.isoformat(),
                    pivot_index=s.pivot_index,
                    price=s.price,
                    direction=s.direction.value,
                    tier=s.tier.value,
                    scope=s.scope.value,
                    confirmed=s.confirmed,
                    confirmation_index=s.confirmation_index,
                    confirmation_delay=s.confirmation_delay,
                    confidence=s.confidence,
                    quality_score=s.quality_score,
                )
            )
            existing.add(key)

        if new_entries:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                for e in new_entries:
                    fh.write(json.dumps(e.to_dict()) + "\n")
        return new_entries

    def load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out


@dataclass
class LiveValidationResult:
    total_logged: int
    total_reviewed: int
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1_score: float
    average_detection_delay_bars: float
    average_price_error: float
    unmatched_predictions: list[dict[str, Any]] = field(default_factory=list)
    missed_reviews: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_logged": self.total_logged,
            "total_reviewed": self.total_reviewed,
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1_score": round(self.f1_score, 4),
            "average_detection_delay_bars": round(self.average_detection_delay_bars, 2),
            "average_price_error": round(self.average_price_error, 6),
            "unmatched_predictions": self.unmatched_predictions,
            "missed_reviews": self.missed_reviews,
        }


def compare_against_review(
    logged: list[dict[str, Any]],
    reviewed: list[dict[str, Any]],
    *,
    price_tolerance: float,
    index_tolerance: int = 2,
) -> LiveValidationResult:
    """Score logged paper swings against a human/benchmark review set.

    Each review entry should have ``pivot_index``, ``price``, ``direction``.
    """
    matched_pred: set[int] = set()
    matched_rev: set[int] = set()
    delays: list[float] = []
    price_errs: list[float] = []

    for pi, pred in enumerate(logged):
        best_ri, best_score = None, float("inf")
        for ri, rev in enumerate(reviewed):
            if ri in matched_rev or pred["direction"] != rev["direction"]:
                continue
            idx_diff = abs(pred["pivot_index"] - rev["pivot_index"])
            price_diff = abs(pred["price"] - rev["price"])
            if idx_diff <= index_tolerance and price_diff <= price_tolerance:
                score = idx_diff + price_diff
                if score < best_score:
                    best_score, best_ri = score, ri
        if best_ri is not None:
            matched_pred.add(pi)
            matched_rev.add(best_ri)
            delays.append(pred.get("confirmation_delay", 0))
            price_errs.append(abs(pred["price"] - reviewed[best_ri]["price"]))

    tp = len(matched_pred)
    fp = len(logged) - tp
    fn = len(reviewed) - len(matched_rev)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return LiveValidationResult(
        total_logged=len(logged),
        total_reviewed=len(reviewed),
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        precision=precision,
        recall=recall,
        f1_score=f1,
        average_detection_delay_bars=sum(delays) / len(delays) if delays else 0.0,
        average_price_error=sum(price_errs) / len(price_errs) if price_errs else 0.0,
        unmatched_predictions=[logged[i] for i in range(len(logged)) if i not in matched_pred],
        missed_reviews=[reviewed[i] for i in range(len(reviewed)) if i not in matched_rev],
    )

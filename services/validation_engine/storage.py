"""Signal outcome storage for the validation feedback loop."""

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class TrackedSignal:
    id: str
    symbol: str
    timeframe: str
    direction: str
    score: int
    confidence: float
    entry_price: float
    stop_loss: float
    take_profit: float
    patterns: list[str] = field(default_factory=list)
    outcome: str | None = None
    pnl_pips: float = 0.0
    exit_price: float | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    closed_at: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class OutcomeStore:
    """Persists tracked signals — file-backed for MVP, swappable for Postgres."""

    def __init__(self, path: str | None = None):
        self._path = Path(path or "data/validation_outcomes.json")
        self._signals: dict[str, TrackedSignal] = {}
        self._load()

    def save(self, signal: TrackedSignal) -> str:
        self._signals[signal.id] = signal
        self._persist()
        return signal.id

    def get(self, signal_id: str) -> TrackedSignal | None:
        return self._signals.get(signal_id)

    def list_all(self, symbol: str | None = None, closed_only: bool = False) -> list[TrackedSignal]:
        results = list(self._signals.values())
        if symbol:
            results = [s for s in results if s.symbol == symbol.upper()]
        if closed_only:
            results = [s for s in results if s.outcome is not None]
        return sorted(results, key=lambda s: s.created_at, reverse=True)

    def update(self, signal: TrackedSignal) -> None:
        self._signals[signal.id] = signal
        self._persist()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text())
            for item in data:
                sig = TrackedSignal(**item)
                self._signals[sig.id] = sig
        except (json.JSONDecodeError, TypeError):
            pass

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = [s.to_dict() for s in self._signals.values()]
        self._path.write_text(json.dumps(payload, indent=2))


def new_signal_id() -> str:
    return str(uuid.uuid4())[:12]

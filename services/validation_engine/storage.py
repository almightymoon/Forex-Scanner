"""Signal outcome storage for the validation feedback loop.

Backends:
- FileOutcomeStore — atomic JSON file (tests / explicit path=)
- DbOutcomeStore — SQLite or PostgreSQL via shared DB adapters (default)

Default production path uses get_database() so outcomes survive multi-process
and multi-host deployments when PostgreSQL is configured.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol


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

    @classmethod
    def from_dict(cls, data: dict) -> "TrackedSignal":
        return cls(
            id=str(data["id"]),
            symbol=str(data["symbol"]),
            timeframe=str(data["timeframe"]),
            direction=str(data["direction"]),
            score=int(data["score"]),
            confidence=float(data["confidence"]),
            entry_price=float(data["entry_price"]),
            stop_loss=float(data["stop_loss"]),
            take_profit=float(data["take_profit"]),
            patterns=list(data.get("patterns") or []),
            outcome=data.get("outcome"),
            pnl_pips=float(data.get("pnl_pips") or 0.0),
            exit_price=float(data["exit_price"]) if data.get("exit_price") is not None else None,
            created_at=str(data.get("created_at") or datetime.now(timezone.utc).isoformat()),
            closed_at=data.get("closed_at"),
        )


class OutcomeStoreProtocol(Protocol):
    def save(self, signal: TrackedSignal) -> str: ...
    def get(self, signal_id: str) -> TrackedSignal | None: ...
    def list_all(self, symbol: str | None = None, closed_only: bool = False) -> list[TrackedSignal]: ...
    def update(self, signal: TrackedSignal) -> None: ...


class FileOutcomeStore:
    """Atomic file-backed store for tests and single-process fallbacks."""

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
                sig = TrackedSignal.from_dict(item)
                self._signals[sig.id] = sig
        except (json.JSONDecodeError, TypeError, KeyError, ValueError):
            pass

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = [s.to_dict() for s in self._signals.values()]
        raw = json.dumps(payload, indent=2)
        # Atomic replace avoids torn reads/writes across processes on one host.
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{self._path.name}.",
            suffix=".tmp",
            dir=str(self._path.parent),
        )
        try:
            with os.fdopen(fd, "w") as tmp:
                tmp.write(raw)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(tmp_name, self._path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise


class DbOutcomeStore:
    """SQLite / PostgreSQL-backed store with idempotent upserts by signal id."""

    def __init__(self, db):
        self._db = db

    def save(self, signal: TrackedSignal) -> str:
        return self._db.upsert_validation_outcome(signal.to_dict())

    def get(self, signal_id: str) -> TrackedSignal | None:
        row = self._db.get_validation_outcome(signal_id)
        return TrackedSignal.from_dict(row) if row else None

    def list_all(self, symbol: str | None = None, closed_only: bool = False) -> list[TrackedSignal]:
        rows = self._db.list_validation_outcomes(symbol=symbol, closed_only=closed_only)
        return [TrackedSignal.from_dict(r) for r in rows]

    def update(self, signal: TrackedSignal) -> None:
        self._db.upsert_validation_outcome(signal.to_dict())


def get_outcome_store(path: str | None = None) -> FileOutcomeStore | DbOutcomeStore:
    """Prefer shared DB (Postgres/SQLite); use file store only when path= is set."""
    if path is not None:
        return FileOutcomeStore(path)
    try:
        from shared.db_factory import get_database

        return DbOutcomeStore(get_database())
    except Exception:
        return FileOutcomeStore()


# Backward-compatible name used by tests (`OutcomeStore(path=...)`).
OutcomeStore = FileOutcomeStore


def new_signal_id() -> str:
    """Full UUID hex — idempotent primary key without truncation collisions."""
    return uuid.uuid4().hex

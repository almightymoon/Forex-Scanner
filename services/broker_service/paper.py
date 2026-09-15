"""Paper broker — journal scanner signals into OOS-parity simulated fills.

Live hook is opt-in (``PAPER_BROKER_ENABLED=true``). Offline twin:
``scripts/paper_broker_1_4_0.py``.

Hard rules:
  - Never set or require SCANNER_EMIT_POLICY.
  - Never mutate frozen 1.4.0 analysis.
  - Fills use ``simulate_trade`` with the same ExecutionConfig as OOS.
  - Live book: at most one open order per (symbol, timeframe); settle on
    candles strictly after ``signal_bar_ts``.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.backtesting_service.execution import (
    ExecutionConfig,
    SimulatedTrade,
    compute_performance_metrics,
    pip_size_for_symbol,
    simulate_trade,
)
from shared.types.models import Candle, ScannerSignal

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT_DIR = ROOT / "benchmarks" / "live" / "paper_broker"
BASE_EXEC = ExecutionConfig("signal_close", "sl_first", 0.0, 0.0, 0.0)
FORWARD_BARS = 20


def paper_broker_enabled() -> bool:
    return os.getenv("PAPER_BROKER_ENABLED", "").lower() in {"1", "true", "yes", "on"}


def _parse_ts(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        ts = value
    else:
        try:
            ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def _candle_ts(candle: Candle) -> datetime | None:
    return _parse_ts(getattr(candle, "timestamp", None))


@dataclass
class PaperOrder:
    id: str
    symbol: str
    timeframe: str
    direction: str
    score: int
    entry_price: float
    stop_loss: float
    take_profit: float
    opened_at: str
    signal_bar_ts: str | None = None
    pipeline_version: str | None = None
    status: str = "open"  # open | closed | cancelled
    outcome: str | None = None
    exit_price: float | None = None
    pnl_pips: float | None = None
    r_multiple: float | None = None
    bars_held: int | None = None
    closed_at: str | None = None
    ambiguous: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PaperOrder":
        fields = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in raw.items() if k in fields})

    @property
    def book_key(self) -> str:
        return f"{self.symbol}|{self.timeframe}"


class PaperBroker:
    """JSONL-backed paper book with OOS-parity settlement."""

    def __init__(
        self,
        out_dir: Path | None = None,
        *,
        config: ExecutionConfig | None = None,
        forward_bars: int = FORWARD_BARS,
        min_score: int | None = None,
        one_open_per_symbol_tf: bool = True,
    ):
        self.out_dir = Path(out_dir or DEFAULT_OUT_DIR)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.open_path = self.out_dir / "open_orders.jsonl"
        self.closed_path = self.out_dir / "closed_orders.jsonl"
        self.intents_path = self.out_dir / "intents.jsonl"
        self.config = config or BASE_EXEC
        self.forward_bars = forward_bars
        self.min_score = min_score
        self.one_open_per_symbol_tf = one_open_per_symbol_tf
        self._open: dict[str, PaperOrder] = {}
        self._load_open()

    def _load_open(self) -> None:
        if not self.open_path.exists():
            return
        for line in self.open_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                order = PaperOrder.from_dict(json.loads(line))
            except (json.JSONDecodeError, TypeError, KeyError):
                continue
            if order.status == "open":
                self._open[order.id] = order

    def _rewrite_open(self) -> None:
        tmp = self.open_path.with_name(f"{self.open_path.stem}.{uuid.uuid4().hex}.tmp")
        with tmp.open("w") as fh:
            for order in self._open.values():
                fh.write(json.dumps(order.to_dict(), default=str) + "\n")
        for _ in range(5):
            try:
                tmp.replace(self.open_path)
                return
            except FileNotFoundError:
                # Concurrent writer may race; rewrite once more.
                with tmp.open("w") as fh:
                    for order in self._open.values():
                        fh.write(json.dumps(order.to_dict(), default=str) + "\n")
        tmp.replace(self.open_path)

    def _append(self, path: Path, row: dict[str, Any]) -> None:
        with path.open("a") as fh:
            fh.write(json.dumps(row, default=str) + "\n")

    def open_orders_for(self, symbol: str, timeframe: str | None = None) -> list[PaperOrder]:
        symbol = symbol.upper()
        out = []
        for order in self._open.values():
            if order.symbol != symbol:
                continue
            if timeframe is not None and order.timeframe != timeframe:
                continue
            out.append(order)
        return out

    def open_from_signal(
        self,
        signal: ScannerSignal,
        *,
        entry_price: float | None = None,
        signal_bar_ts: str | None = None,
    ) -> PaperOrder | None:
        """Journal a paper order from a live/offline scanner signal."""
        if signal.direction is None:
            return None
        direction = (
            signal.direction.value
            if hasattr(signal.direction, "value")
            else str(signal.direction)
        ).lower()
        if direction not in {"buy", "sell"}:
            return None
        if signal.stop_loss is None or signal.take_profit_1 is None:
            return None
        if self.min_score is not None and signal.score < self.min_score:
            return None

        if entry_price is None:
            low = signal.entry_zone_low
            high = signal.entry_zone_high or low
            if low is None:
                return None
            entry_price = (low + high) / 2.0

        tf = (
            signal.timeframe.value
            if hasattr(signal.timeframe, "value")
            else str(signal.timeframe)
        )
        symbol = signal.symbol.upper()

        if self.one_open_per_symbol_tf and self.open_orders_for(symbol, tf):
            return None

        # Same bar fingerprint — avoid reopen storms if dedupe flag is off.
        sig_ts = signal_bar_ts
        if sig_ts:
            for existing in self.open_orders_for(symbol, tf):
                if existing.signal_bar_ts == sig_ts and existing.direction == direction:
                    return None

        now = datetime.now(timezone.utc).isoformat()
        order = PaperOrder(
            id=str(uuid.uuid4()),
            symbol=symbol,
            timeframe=tf,
            direction=direction,
            score=int(signal.score),
            entry_price=float(entry_price),
            stop_loss=float(signal.stop_loss),
            take_profit=float(signal.take_profit_1),
            opened_at=now,
            signal_bar_ts=sig_ts or (
                signal.created_at.isoformat()
                if getattr(signal, "created_at", None) is not None
                else None
            ),
            pipeline_version=getattr(signal, "pipeline_version", None),
        )
        self._open[order.id] = order
        self._rewrite_open()
        self._append(self.intents_path, {"event": "open", **order.to_dict()})
        return order

    def cancel_order(self, order_id: str, *, reason: str = "cancelled") -> PaperOrder | None:
        order = self._open.get(order_id)
        if order is None:
            return None
        order.status = "cancelled"
        order.outcome = reason
        order.closed_at = datetime.now(timezone.utc).isoformat()
        del self._open[order_id]
        self._rewrite_open()
        self._append(self.closed_path, order.to_dict())
        self._append(self.intents_path, {"event": "cancel", **order.to_dict()})
        return order

    def prune_duplicate_opens(self) -> dict[str, int]:
        """Keep newest open per (symbol, timeframe); cancel the rest."""
        by_key: dict[str, list[PaperOrder]] = {}
        for order in list(self._open.values()):
            by_key.setdefault(order.book_key, []).append(order)
        cancelled = 0
        kept = 0
        for group in by_key.values():
            group.sort(key=lambda o: o.opened_at or "", reverse=True)
            kept += 1
            for dup in group[1:]:
                self.cancel_order(dup.id, reason="dedupe_prune")
                cancelled += 1
        return {"kept": kept, "cancelled": cancelled, "open": len(self._open)}

    def settle_with_forward(
        self,
        order: PaperOrder,
        forward: list[Candle],
    ) -> PaperOrder | None:
        """Close one order using bars AFTER the signal bar (OOS parity)."""
        if order.status != "open" or order.id not in self._open:
            return None
        if not forward:
            return None

        pip = pip_size_for_symbol(order.symbol)
        window = forward[: self.forward_bars]
        if not window:
            return None

        # Keep open until SL/TP is touched or the full forward window exists.
        if len(forward) < self.forward_bars and not self._touched_levels(order, window):
            return None

        sim: SimulatedTrade = simulate_trade(
            direction=order.direction,
            entry=order.entry_price,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            forward_bars=window,
            pip=pip,
            score=order.score,
            config=self.config,
        )

        closed_at = (
            window[min(sim.bars_held, len(window)) - 1].timestamp.isoformat()
            if window and sim.bars_held
            else datetime.now(timezone.utc).isoformat()
        )
        order.status = "closed"
        order.outcome = sim.outcome
        order.exit_price = sim.exit_price
        order.pnl_pips = round(sim.pnl_pips, 2)
        order.r_multiple = round(sim.r_multiple, 4)
        order.bars_held = sim.bars_held
        order.closed_at = closed_at
        order.ambiguous = sim.ambiguous

        del self._open[order.id]
        self._rewrite_open()
        self._append(self.closed_path, order.to_dict())
        self._append(self.intents_path, {"event": "close", **order.to_dict()})
        return order

    @staticmethod
    def _touched_levels(order: PaperOrder, bars: list[Candle]) -> bool:
        for bar in bars:
            if order.direction == "buy":
                if bar.low <= order.stop_loss or bar.high >= order.take_profit:
                    return True
            else:
                if bar.high >= order.stop_loss or bar.low <= order.take_profit:
                    return True
        return False

    def evaluate_open(self, symbol: str, candles: list[Candle]) -> list[PaperOrder]:
        """Settle open paper orders for ``symbol`` against latest candles."""
        closed: list[PaperOrder] = []
        symbol = symbol.upper()
        for order in list(self._open.values()):
            if order.symbol != symbol:
                continue
            forward = self._forward_after_signal(order, candles)
            if not forward:
                continue
            result = self.settle_with_forward(order, forward)
            if result is not None:
                closed.append(result)
        return closed

    def _forward_after_signal(
        self, order: PaperOrder, candles: list[Candle]
    ) -> list[Candle]:
        """Return candles strictly after the signal bar. Empty ⇒ not ready."""
        if not candles:
            return []
        signal_ts = _parse_ts(order.signal_bar_ts)
        if signal_ts is None:
            # No anchor — require a full trailing window and treat it as forward.
            return list(candles[-self.forward_bars :]) if len(candles) > 1 else []

        forward: list[Candle] = []
        for c in candles:
            ts = _candle_ts(c)
            if ts is not None and ts > signal_ts:
                forward.append(c)
        return forward

    def summary(self) -> dict[str, Any]:
        closed: list[SimulatedTrade] = []
        cancelled = 0
        if self.closed_path.exists():
            for line in self.closed_path.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("status") == "cancelled" or row.get("outcome") == "dedupe_prune":
                    cancelled += 1
                    continue
                closed.append(
                    SimulatedTrade(
                        entry_price=float(row["entry_price"]),
                        exit_price=float(row.get("exit_price") or row["entry_price"]),
                        direction=row["direction"],
                        outcome=row.get("outcome") or "breakeven",
                        pnl_pips=float(row.get("pnl_pips") or 0),
                        pnl_price=0.0,
                        risk_price=1.0,
                        r_multiple=float(row.get("r_multiple") or 0),
                        score=int(row.get("score") or 0),
                        ambiguous=bool(row.get("ambiguous")),
                        bars_held=int(row.get("bars_held") or 0),
                    )
                )
        metrics = compute_performance_metrics(closed).to_dict() if closed else {
            "total_trades": 0,
            "expectancy": 0.0,
            "win_rate": 0.0,
        }
        return {
            "open": len(self._open),
            "closed": len(closed),
            "cancelled": cancelled,
            "metrics": metrics,
            "out_dir": str(self.out_dir),
        }


_BROKER: PaperBroker | None = None


def get_paper_broker() -> PaperBroker:
    global _BROKER
    if _BROKER is None:
        _BROKER = PaperBroker()
    return _BROKER


def reset_paper_broker_singleton() -> None:
    """Test/ops helper after pruning the on-disk book."""
    global _BROKER
    _BROKER = None

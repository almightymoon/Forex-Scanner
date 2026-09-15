"""Paper broker — journal scanner signals into OOS-parity simulated fills.

Live hook is opt-in (``PAPER_BROKER_ENABLED=true``). Offline twin:
``scripts/paper_broker_1_4_0.py``.

Hard rules:
  - Never set or require SCANNER_EMIT_POLICY.
  - Never mutate frozen 1.4.0 analysis.
  - Fills use ``simulate_trade`` with the same ExecutionConfig as OOS.
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
    status: str = "open"  # open | closed
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


class PaperBroker:
    """JSONL-backed paper book with OOS-parity settlement."""

    def __init__(
        self,
        out_dir: Path | None = None,
        *,
        config: ExecutionConfig | None = None,
        forward_bars: int = FORWARD_BARS,
        min_score: int | None = None,
    ):
        self.out_dir = Path(out_dir or DEFAULT_OUT_DIR)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.open_path = self.out_dir / "open_orders.jsonl"
        self.closed_path = self.out_dir / "closed_orders.jsonl"
        self.intents_path = self.out_dir / "intents.jsonl"
        self.config = config or BASE_EXEC
        self.forward_bars = forward_bars
        self.min_score = min_score
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
        tmp = self.open_path.with_suffix(".tmp")
        with tmp.open("w") as fh:
            for order in self._open.values():
                fh.write(json.dumps(order.to_dict(), default=str) + "\n")
        tmp.replace(self.open_path)

    def _append(self, path: Path, row: dict[str, Any]) -> None:
        with path.open("a") as fh:
            fh.write(json.dumps(row, default=str) + "\n")

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
        now = datetime.now(timezone.utc).isoformat()
        order = PaperOrder(
            id=str(uuid.uuid4()),
            symbol=signal.symbol.upper(),
            timeframe=tf,
            direction=direction,
            score=int(signal.score),
            entry_price=float(entry_price),
            stop_loss=float(signal.stop_loss),
            take_profit=float(signal.take_profit_1),
            opened_at=now,
            signal_bar_ts=signal_bar_ts or (
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
            if forward is None:
                continue
            result = self.settle_with_forward(order, forward)
            if result is not None:
                closed.append(result)
        return closed

    def _forward_after_signal(
        self, order: PaperOrder, candles: list[Candle]
    ) -> list[Candle] | None:
        if not candles:
            return None
        if order.signal_bar_ts:
            idx = None
            for i, c in enumerate(candles):
                ts = c.timestamp.isoformat() if hasattr(c.timestamp, "isoformat") else str(c.timestamp)
                if ts == order.signal_bar_ts or ts.startswith(order.signal_bar_ts[:19]):
                    idx = i
                    break
            if idx is None:
                # Signal bar not in window — use all candles as forward (conservative live).
                return list(candles[-self.forward_bars :])
            return list(candles[idx + 1 :])
        return list(candles[-self.forward_bars :])

    def summary(self) -> dict[str, Any]:
        closed: list[SimulatedTrade] = []
        if self.closed_path.exists():
            for line in self.closed_path.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
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
            "metrics": metrics,
            "out_dir": str(self.out_dir),
        }


_BROKER: PaperBroker | None = None


def get_paper_broker() -> PaperBroker:
    global _BROKER
    if _BROKER is None:
        _BROKER = PaperBroker()
    return _BROKER

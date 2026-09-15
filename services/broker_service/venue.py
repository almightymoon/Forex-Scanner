"""Venue broker interface — live order routing stubs (Phase 2).

Market data stays on Twelve Data / Polygon. Execution venues are separate and
default to disabled. Paper fills use ``PaperBroker``; these classes are for
real broker APIs only.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


OrderSide = Literal["buy", "sell"]
OrderType = Literal["market"]
OrderStatus = Literal["rejected", "submitted", "filled", "cancelled"]


@dataclass
class VenueOrderRequest:
    symbol: str
    side: OrderSide
    units: float
    order_type: OrderType = "market"
    stop_loss: float | None = None
    take_profit: float | None = None
    client_tag: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class VenueOrderResult:
    venue: str
    status: OrderStatus
    symbol: str
    side: OrderSide
    units: float
    message: str
    venue_order_id: str | None = None
    fill_price: float | None = None
    submitted_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BrokerVenue(ABC):
    """Abstract live venue. Implementations must refuse orders unless explicitly armed."""

    name: str

    @abstractmethod
    def is_ready(self) -> bool:
        ...

    @abstractmethod
    def place_market_order(self, req: VenueOrderRequest) -> VenueOrderResult:
        ...


def venue_orders_armed() -> bool:
    """Live venue orders require an explicit second switch (default off)."""
    return os.getenv("BROKER_VENUE_ORDERS_ENABLED", "").lower() in {"1", "true", "yes", "on"}


def selected_venue_name() -> str:
    return (os.getenv("BROKER_VENUE", "none") or "none").strip().lower()

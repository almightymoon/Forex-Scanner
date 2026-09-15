"""Phase-2-prep paper broker — simulated fills, not live venue APIs.

Does not enable SCANNER_EMIT_POLICY and does not modify frozen 1.4.0 analysis.
Opt-in via PAPER_BROKER_ENABLED=true.

Live venue stubs (OANDA / MT5) refuse orders unless BROKER_VENUE_ORDERS_ENABLED
is explicitly set — and even then current stubs return not-implemented.
"""

from .factory import get_broker_venue, venue_status
from .paper import PaperBroker, PaperOrder, get_paper_broker, paper_broker_enabled
from .venue import VenueOrderRequest, VenueOrderResult, venue_orders_armed

__all__ = [
    "PaperBroker",
    "PaperOrder",
    "paper_broker_enabled",
    "get_paper_broker",
    "get_broker_venue",
    "venue_status",
    "VenueOrderRequest",
    "VenueOrderResult",
    "venue_orders_armed",
]

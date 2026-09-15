"""Phase-2-prep paper broker — simulated fills, not live venue APIs.

Does not enable SCANNER_EMIT_POLICY and does not modify frozen 1.4.0 analysis.
Opt-in via PAPER_BROKER_ENABLED=true.
"""

from .paper import PaperBroker, PaperOrder, paper_broker_enabled, get_paper_broker

__all__ = [
    "PaperBroker",
    "PaperOrder",
    "paper_broker_enabled",
    "get_paper_broker",
]

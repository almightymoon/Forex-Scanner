"""Event types for the FX Navigators event bus."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import json


@dataclass
class Event:
    type: str
    payload: dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = "scanner"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "source": self.source,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class EventTypes:
    CANDLE_RECEIVED = "candle.received"
    INDICATORS_COMPUTED = "indicators.computed"
    SMC_DETECTED = "smc.detected"
    SCAN_COMPLETED = "scan.completed"
    SIGNAL_ALERT = "signal.alert"
    STRATEGY_TRIGGERED = "strategy.triggered"

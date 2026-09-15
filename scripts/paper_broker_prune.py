#!/usr/bin/env python3
"""Prune duplicate live paper opens (keep newest per symbol|timeframe)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.broker_service.paper import PaperBroker, reset_paper_broker_singleton


def main() -> int:
    reset_paper_broker_singleton()
    broker = PaperBroker()
    before = broker.summary()
    result = broker.prune_duplicate_opens()
    after = broker.summary()
    print(json.dumps({"before": before, "prune": result, "after": after}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

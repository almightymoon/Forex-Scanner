#!/usr/bin/env python3
"""Summarize the live paper-broker book (open / closed / metrics)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.broker_service.paper import PaperBroker, paper_broker_enabled


def main() -> int:
    broker = PaperBroker()
    summary = broker.summary()
    payload = {
        "PAPER_BROKER_ENABLED": paper_broker_enabled(),
        "SCANNER_EMIT_POLICY": os.getenv("SCANNER_EMIT_POLICY") or None,
        **summary,
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

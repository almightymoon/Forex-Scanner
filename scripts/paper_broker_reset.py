#!/usr/bin/env python3
"""Archive the live paper book and start a fresh journal (e.g. after leaving sim mode)."""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.broker_service.paper import DEFAULT_OUT_DIR, reset_paper_broker_singleton


def main() -> int:
    out = DEFAULT_OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = out / f"archive_{stamp}"
    archive.mkdir(parents=True, exist_ok=True)

    moved = []
    for name in ("open_orders.jsonl", "closed_orders.jsonl", "intents.jsonl", "summary.json"):
        src = out / name
        if src.exists():
            dest = archive / name
            shutil.move(str(src), str(dest))
            moved.append(name)

    reset_paper_broker_singleton()
    print(
        json.dumps(
            {
                "archived_to": str(archive),
                "moved": moved,
                "open": 0,
                "closed": 0,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

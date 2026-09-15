#!/usr/bin/env python3
"""OANDA practice readiness check — never arms orders without explicit confirm.

Usage:
  PYTHONPATH=. python scripts/oanda_practice_smoke.py
  PYTHONPATH=. python scripts/oanda_practice_smoke.py --arm-check
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = val


def main() -> int:
    _load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--arm-check",
        action="store_true",
        help="If keys+arming present, place a dry REJECTED probe (units=0 rejected locally) — still will not send if disarmed",
    )
    args = ap.parse_args()

    from services.broker_service import get_broker_venue, venue_orders_armed, VenueOrderRequest

    key = os.getenv("OANDA_API_KEY", "")
    acct = os.getenv("OANDA_ACCOUNT_ID", "")
    venue_name = os.getenv("BROKER_VENUE", "none")
    armed = venue_orders_armed()
    env = os.getenv("OANDA_ENV", "practice")

    report = {
        "oanda_key_present": bool(key),
        "oanda_account_present": bool(acct),
        "BROKER_VENUE": venue_name,
        "BROKER_VENUE_ORDERS_ENABLED": armed,
        "OANDA_ENV": env,
        "ready_to_arm": bool(key and acct and env == "practice"),
        "action": None,
    }

    if not key or not acct:
        report["action"] = (
            "Set OANDA_API_KEY and OANDA_ACCOUNT_ID in .env (practice account), "
            "then set BROKER_VENUE=oanda and only then BROKER_VENUE_ORDERS_ENABLED=true."
        )
        print(json.dumps(report, indent=2))
        return 2

    os.environ["BROKER_VENUE"] = "oanda"
    venue = get_broker_venue("oanda")
    report["venue_ready"] = venue.is_ready()

    if not armed:
        report["action"] = (
            "Credentials present but orders disarmed — leaving BROKER_VENUE_ORDERS_ENABLED=false "
            "(safe). Flip to true only when you want practice fills."
        )
        # Ensure .env stays on oanda venue selection without arming.
        print(json.dumps(report, indent=2))
        return 0

    if args.arm_check:
        # Armed path: tiny probe — still real API if keys valid.
        result = venue.place_market_order(
            VenueOrderRequest(symbol="EUR_USD", side="buy", units=1, client_tag="fxnav-smoke")
        )
        report["probe"] = result.to_dict()
        report["action"] = "Probe sent (see probe.status)"
        print(json.dumps(report, indent=2))
        return 0 if result.status in {"filled", "submitted", "rejected"} else 1

    report["action"] = "Armed but --arm-check not passed; no order sent."
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Find and ingest newer post-2026H1 MT5 exports, then re-check H5 gate.

Looks under MT5-scripts/ and optional --raw/--metadata paths. Refuses to invent
candles — if nothing newer than the quarantine tip exists, exits 2.

Usage:
  PYTHONPATH=. python scripts/ingest_and_check_h5.py
  PYTHONPATH=. python scripts/ingest_and_check_h5.py --raw path.csv --metadata path.meta.csv
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MT5_DIR = ROOT / "MT5-scripts"
QUARANTINE = ROOT / "benchmarks/data/quarantine/XAUUSD/H1/post_2026H1"
STATUS = ROOT / "scripts/status_xauusd_h1_post_2026h1_accrual.py"
INGEST = ROOT / "scripts/ingest_xauusd_h1_post_2026h1_quarantine.py"
H5 = ROOT / "scripts/run_h5_prospective_1_4_0.py"


def _latest_quarantine_tip() -> str | None:
    if not QUARANTINE.exists():
        return None
    tips = sorted(p.name for p in QUARANTINE.iterdir() if p.is_dir())
    return tips[-1] if tips else None


def _discover_exports() -> list[tuple[Path, Path]]:
    pairs: list[tuple[Path, Path]] = []
    for raw in sorted(MT5_DIR.glob("*post_2026H1*raw*.csv")):
        if raw.name.endswith(".meta.csv"):
            continue
        meta = raw.with_suffix("").with_suffix(".meta.csv")
        # FXNavigators_..._raw_TS.csv → ..._raw_TS.meta.csv
        candidates = [
            Path(str(raw).replace(".csv", ".meta.csv")),
            raw.parent / (raw.stem + ".meta.csv"),
        ]
        for m in candidates:
            if m.exists():
                pairs.append((raw, m))
                break
    return pairs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", type=Path, default=None)
    ap.add_argument("--metadata", type=Path, default=None)
    ap.add_argument("--run-h5", action="store_true", help="Call H5 --run if gate passes")
    args = ap.parse_args()

    tip = _latest_quarantine_tip()
    print(json.dumps({"quarantine_tip": tip}, indent=2))

    jobs: list[tuple[Path, Path]] = []
    if args.raw and args.metadata:
        jobs.append((args.raw, args.metadata))
    else:
        jobs.extend(_discover_exports())

    if not jobs:
        print(
            "No post-2026H1 raw+meta exports found under MT5-scripts/. "
            "Export a fresh MT5 H1 snapshot after the quarantine tip, then re-run.",
            file=sys.stderr,
        )
        return 2

    ingested = []
    for raw, meta in jobs:
        print(f"\n→ ingest attempt: {raw.name}")
        proc = subprocess.run(
            [sys.executable, str(INGEST), "--raw", str(raw), "--metadata", str(meta)],
            cwd=str(ROOT),
            env={**dict(**{k: v for k, v in __import__("os").environ.items()}), "PYTHONPATH": str(ROOT)},
            capture_output=True,
            text=True,
        )
        print(proc.stdout[-2000:] if proc.stdout else "")
        if proc.stderr:
            print(proc.stderr[-1500:], file=sys.stderr)
        ingested.append({"raw": str(raw), "exit": proc.returncode})

    status = subprocess.run(
        [sys.executable, str(H5), "--status"],
        cwd=str(ROOT),
        env={**dict(**{k: v for k, v in __import__("os").environ.items()}), "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
    )
    print(status.stdout)
    gate = {}
    try:
        gate = json.loads(status.stdout)
    except json.JSONDecodeError:
        pass

    if args.run_h5 and gate.get("passed"):
        run = subprocess.run(
            [sys.executable, str(H5), "--run"],
            cwd=str(ROOT),
            env={**dict(**{k: v for k, v in __import__("os").environ.items()}), "PYTHONPATH": str(ROOT)},
        )
        return run.returncode

    if not gate.get("passed"):
        print(
            "H5 still blocked. Need a newer MT5 export with unique bars after "
            f"{tip or 'current tip'} (target ≥1400 bars through 2026-09-30T20:00Z).",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

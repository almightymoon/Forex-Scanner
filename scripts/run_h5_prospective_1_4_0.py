#!/usr/bin/env python3
"""H5 prospective shadow of frozen 1.4.0 — runs only when accrual gate passes.

Does not modify analysis, does not set SCANNER_EMIT_POLICY, and does not
overwrite retrospective ``validation/`` artifacts.

Usage:
  python scripts/run_h5_prospective_1_4_0.py --status
  python scripts/run_h5_prospective_1_4_0.py --run   # exits non-zero if gate fails
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.pop("SCANNER_EMIT_POLICY", None)

OUT_DIR = ROOT / "validation_h5_prospective"
STATUS_JSON = ROOT / "benchmarks" / "reports" / "XAUUSD_H1_post_2026H1_accrual_status.json"
QUARANTINE = ROOT / "benchmarks" / "data" / "quarantine" / "XAUUSD" / "H1" / "post_2026H1"


def refresh_accrual_status() -> dict[str, Any]:
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "status_xauusd_h1_post_2026h1_accrual.py")],
        cwd=str(ROOT),
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )
    if not STATUS_JSON.exists():
        return {"all_requirements_passed": False, "error": "status file missing"}
    return json.loads(STATUS_JSON.read_text())


def gate_report(status: dict[str, Any]) -> dict[str, Any]:
    gates = status.get("gates") or {}
    coverage = status.get("coverage") or {}
    passed = bool(gates.get("all_requirements_passed"))
    return {
        "passed": passed,
        "unique_bars": coverage.get("unique_normalized_h1_bars"),
        "bars_remaining": gates.get("bars_remaining"),
        "latest_utc": coverage.get("last_utc"),
        "required_bars": gates.get("required_unique_h1_bars", 1400),
        "required_coverage_date": gates.get("required_not_before_utc"),
        "bars_gate_passed": gates.get("bars_gate_passed"),
        "date_gate_passed": gates.get("date_gate_passed"),
        "status": status.get("status"),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_prospective_csv() -> Path | None:
    """Locate a locked prospective CSV if present; else None."""
    candidates = [
        ROOT / "benchmarks/data/prospective/XAUUSD/H1_post_2026H1/XAUUSD_H1_post_2026H1.real.csv.gz",
        ROOT / "benchmarks/data/prospective/XAUUSD/H1_post_2026H1/XAUUSD_H1_post_2026H1.csv",
    ]
    for c in candidates:
        if c.exists():
            return c
    # Quarantine may only have tranche CSVs until lock step.
    if QUARANTINE.exists():
        csvs = sorted(QUARANTINE.rglob("*.csv"))
        if csvs:
            return csvs[-1]
    return None


def run_h5(csv_path: Path) -> dict[str, Any]:
    """Run frozen 1.4.0 OOS-parity paper fills on the prospective CSV."""
    from scripts.paper_broker_1_4_0 import run_paper, load_candles

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset_sha = _sha256_file(csv_path)
    lock = {
        "dataset_id": "xauusd_h1_post_2026h1_prospective",
        "source_path": str(csv_path.relative_to(ROOT)) if csv_path.is_relative_to(ROOT) else str(csv_path),
        "sha256": dataset_sha,
        "locked_at": datetime.now(timezone.utc).isoformat(),
        "note": "Prospective H5 lock — does not overwrite validation/ retrospective OOS.",
    }
    (OUT_DIR / "dataset_lock.json").write_text(json.dumps(lock, indent=2) + "\n")

    candles = load_candles(csv_path, "XAUUSD")
    summary = run_paper(
        candles,
        start=None,
        end=None,
        min_score=70,
        out_dir=OUT_DIR / "paper_fills",
    )
    report = {
        "experiment": "H5",
        "pipeline_version": "1.4.0",
        "verdict": "COMPLETE — prospective shadow only (does not reverse 1.4.0 FAILED OOS)",
        "dataset_lock": lock,
        "summary": summary,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (OUT_DIR / "report.json").write_text(json.dumps(report, indent=2) + "\n")

    md = OUT_DIR / "EXPERIMENT_REPORT_H5.md"
    md.write_text(
        "\n".join(
            [
                "# Experiment Report — H5 Prospective Shadow (1.4.0)",
                "",
                f"**Generated:** {report['generated_at']}",
                f"**Dataset SHA-256:** `{dataset_sha}`",
                f"**Source:** `{lock['source_path']}`",
                "",
                "## Verdict",
                "",
                report["verdict"],
                "",
                "## Metrics",
                "",
                "```json",
                json.dumps(summary.get("metrics", {}), indent=2),
                "```",
                "",
                "## Non-claims",
                "",
                "- Does not reverse the frozen 1.4.0 FAILED OOS verdict.",
                "- Does not enable SCANNER_EMIT_POLICY.",
                "- Does not retune DecisionEngine / zones / ranking.",
                "",
            ]
        )
        + "\n"
    )
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--status", action="store_true", help="Print accrual gate status")
    g.add_argument("--run", action="store_true", help="Run H5 if gate passes")
    args = ap.parse_args()

    status = refresh_accrual_status()
    gate = gate_report(status)
    print(json.dumps(gate, indent=2))

    if args.status:
        return 0 if gate["passed"] else 2

    if not gate["passed"]:
        print(
            "\nH5 BLOCKED — accrual gate not met. "
            "Ingest more post-2026H1 candles, then re-run --status.",
            file=sys.stderr,
        )
        return 2

    csv_path = find_prospective_csv()
    if csv_path is None:
        print(
            "\nH5 gate passed but no prospective CSV found under "
            "benchmarks/data/prospective/ or quarantine. Lock the dataset first.",
            file=sys.stderr,
        )
        return 3

    report = run_h5(csv_path)
    print(json.dumps({"ok": True, "report": str(OUT_DIR / "report.json"), "fills": report["summary"].get("fills")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

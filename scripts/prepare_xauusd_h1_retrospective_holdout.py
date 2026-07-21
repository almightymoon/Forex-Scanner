#!/usr/bin/env python3
"""Prepare a contamination-aware retrospective XAUUSD H1 holdout source.

This workflow freezes a chronological prefix of the full MT5 history that ends
strictly before the already-exposed 2024-07-15 canonical boundary, with an
additional 48-bar embargo.

Classification: RETROSPECTIVE_HOLDOUT

Safety:
- does not import or execute swing-engine detection;
- does not load labels or predictions;
- does not evaluate candidates or baselines;
- refuses ambiguous timezone, overlap, or provenance states;
- refuses to overwrite an existing output package.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.types.models import Candle, Timeframe  # noqa: E402
from swing_engine.benchmark_data import (  # noqa: E402
    write_canonical_candles_csv,
)


ROOT = Path(__file__).resolve().parents[1]

EXPECTED_COLUMNS = [
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "tick_volume",
    "volume",
    "spread",
    "symbol",
    "timeframe",
]

EXPECTED_ROW_COUNT = 24099
EMBARGO_BARS = 48
PREFERRED_TIMEZONES = (
    "Europe/Athens",
    "Europe/Helsinki",
    "Europe/Bucharest",
)
CONVERSION_REFERENCE_TIMEZONE = "Europe/Athens"
TIMEZONE_SCHEDULE_CLASSIFICATION = (
    "EET_EEST_EQUIVALENT_OFFSET_SCHEDULE"
)

SOURCE_ID = "WEALTHTEX_MT5_XAUUSD_VX"
PRICE_BASIS = "BID"
PACKAGE_STATUS = "RETROSPECTIVE_HOLDOUT_SOURCE_FROZEN_NOT_LABELED"
CLASSIFICATION = "RETROSPECTIVE_HOLDOUT"

RAW_OUT_NAME = "XAUUSD_H1_2022_2024_raw.csv"
CANONICAL_OUT_NAME = "XAUUSD_H1_2022_2024.real.csv.gz"
AUDIT_OUT_NAME = "source_audit.json"
MANIFEST_OUT_NAME = "source_manifest.json"
README_OUT_NAME = "README.md"

PROTOCOL_ID = "XAUUSD_H1_2022_2024_RETROSPECTIVE_LOCKED_V1"


class HoldoutError(SystemExit):
    """Fail-closed refusal."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def git_output(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise HoldoutError(
            f"REFUSED: git {' '.join(args)} failed: {result.stderr.strip()}"
        )
    return (result.stdout or "").strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw",
        type=Path,
        required=True,
        help="Full MT5 FXNavigators_XAUUSD_H1.csv export",
    )
    parser.add_argument(
        "--canonical-overlap",
        type=Path,
        default=(
            ROOT
            / "benchmarks"
            / "data"
            / "real"
            / "XAUUSD"
            / "H1"
            / "XAUUSD_H1.real.csv.gz"
        ),
        help="Already-exposed canonical UTC candle file",
    )
    parser.add_argument(
        "--duplicate-copy",
        type=Path,
        default=ROOT / "chart_csv" / "FXNavigators_XAUUSD_H1.csv",
        help="Tracked duplicate copy used for byte-identity checks",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=(
            ROOT
            / "benchmarks"
            / "data"
            / "retrospective"
            / "XAUUSD"
            / "H1_2022_2024_v1"
        ),
    )
    parser.add_argument(
        "--protocol-output",
        type=Path,
        default=(
            ROOT
            / "benchmarks"
            / "protocols"
            / "XAUUSD_H1_2022_2024_retrospective_locked_protocol.json"
        ),
    )
    parser.add_argument(
        "--audit-only",
        action="store_true",
        help="Write only the audit JSON; do not publish the source package",
    )
    parser.add_argument(
        "--audit-output",
        type=Path,
        help="Optional path for audit JSON when using --audit-only",
    )
    return parser.parse_args()


def parse_server_timestamp(value: str) -> datetime:
    return datetime.strptime(value.strip(), "%Y.%m.%d %H:%M:%S")


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def utc_text(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def dec(value: str) -> Decimal:
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, AttributeError) as exc:
        raise HoldoutError(
            f"REFUSED: non-decimal numeric value {value!r}"
        ) from exc


@dataclass
class RawRow:
    index: int
    line_bytes: bytes
    timestamp_raw: str
    timestamp_naive: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    tick_volume: int
    volume: int
    spread: Decimal
    symbol: str
    timeframe: str


def provenance_audit(duplicate_copy: Path) -> dict[str, Any]:
    tracked = bool(
        git_output(
            "ls-files",
            "--",
            display_path(duplicate_copy),
            check=False,
        )
    )

    first_commit = None
    first_subject = None
    first_date = None
    if tracked:
        log = git_output(
            "log",
            "--diff-filter=A",
            "--follow",
            "--format=%H%x09%ai%x09%s",
            "--",
            display_path(duplicate_copy),
            check=False,
        )
        if log:
            first_line = log.splitlines()[-1]
            parts = first_line.split("\t")
            if len(parts) == 3:
                first_commit, first_date, first_subject = parts

    references = {
        "FXNavigators_XAUUSD_H1.csv": sorted(
            {
                display_path(Path(p))
                for p in git_output(
                    "grep",
                    "-l",
                    "FXNavigators_XAUUSD_H1.csv",
                    check=False,
                ).splitlines()
                if p.strip()
            }
        ),
        "XAUUSD_H1.real.csv.gz": sorted(
            {
                display_path(Path(p))
                for p in git_output(
                    "grep",
                    "-l",
                    "XAUUSD_H1.real.csv.gz",
                    check=False,
                ).splitlines()
                if p.strip()
            }
        ),
    }

    # Honest caveat: grep absence is not proof humans never viewed pre-boundary bars.
    return {
        "chart_csv_tracked": tracked,
        "chart_csv_path": display_path(duplicate_copy),
        "first_git_appearance": {
            "commit": first_commit,
            "author_date": first_date,
            "subject": first_subject,
        },
        "repository_references": references,
        "caveats": [
            (
                "Absence of a repository reference is not proof that humans "
                "never viewed pre-2024-07-15 bars outside Git."
            ),
            (
                "The full MT5 export existed in chart_csv and Common/Files "
                "before this retrospective package was constructed; the source "
                "is therefore not a prospective forward test."
            ),
            (
                "benchmarks/data/real/XAUUSD/H1/XAUUSD_H1.data_quality.json "
                "records excluded_source_rows=15416 starting at "
                "2024.07.15 10:00:00; prior scripts intentionally started the "
                "exposed canonical series at that boundary."
            ),
            (
                "No tracked label file, manifest window, or quarantine tranche "
                "references UTC bars before 2024-07-15T07:00:00Z, but that does "
                "not prove the earlier interval was never inspected informally."
            ),
        ],
    }


def load_raw_rows(path: Path) -> tuple[list[RawRow], bytes, list[str]]:
    raw_bytes = path.read_bytes()
    if b"\r\n" not in raw_bytes:
        raise HoldoutError(
            "REFUSED: expected CRLF MT5 export line endings"
        )

    lines = raw_bytes.split(b"\r\n")
    # Trailing newline produces a final empty segment.
    if lines and lines[-1] == b"":
        lines = lines[:-1]
    if not lines:
        raise HoldoutError("REFUSED: empty raw source")

    header_line = lines[0].decode("utf-8-sig")
    header = next(csv.reader([header_line]))
    if header != EXPECTED_COLUMNS:
        raise HoldoutError(
            "REFUSED: unexpected columns "
            f"{header}; expected {EXPECTED_COLUMNS}"
        )

    rows: list[RawRow] = []
    for index, line in enumerate(lines[1:]):
        text = line.decode("utf-8")
        parsed = next(csv.reader([text]))
        if len(parsed) != len(EXPECTED_COLUMNS):
            raise HoldoutError(
                f"REFUSED: row {index} has {len(parsed)} fields"
            )
        record = dict(zip(EXPECTED_COLUMNS, parsed))
        try:
            tick_volume = int(record["tick_volume"])
            volume = int(record["volume"])
        except ValueError as exc:
            raise HoldoutError(
                f"REFUSED: row {index} has non-integer volume fields"
            ) from exc

        open_ = dec(record["open"])
        high = dec(record["high"])
        low = dec(record["low"])
        close = dec(record["close"])
        spread = dec(record["spread"])

        if any(
            not math.isfinite(float(value))
            for value in (open_, high, low, close, spread)
        ):
            raise HoldoutError(
                f"REFUSED: row {index} has non-finite OHLC/spread"
            )

        rows.append(
            RawRow(
                index=index,
                line_bytes=line + b"\r\n",
                timestamp_raw=record["timestamp"],
                timestamp_naive=parse_server_timestamp(
                    record["timestamp"]
                ),
                open=open_,
                high=high,
                low=low,
                close=close,
                tick_volume=tick_volume,
                volume=volume,
                spread=spread,
                symbol=record["symbol"].strip(),
                timeframe=record["timeframe"].strip(),
            )
        )

    header_bytes = lines[0] + b"\r\n"
    return rows, raw_bytes, [header_bytes.decode("utf-8-sig")]


def validate_raw_identity(rows: list[RawRow]) -> dict[str, Any]:
    if len(rows) != EXPECTED_ROW_COUNT:
        raise HoldoutError(
            f"REFUSED: expected {EXPECTED_ROW_COUNT} rows, found {len(rows)}"
        )

    symbols = {row.symbol for row in rows}
    timeframes = {row.timeframe for row in rows}
    if symbols != {"XAUUSD.vx"}:
        raise HoldoutError(
            f"REFUSED: unexpected symbol set {sorted(symbols)}"
        )
    if timeframes != {"PERIOD_H1"}:
        raise HoldoutError(
            f"REFUSED: unexpected timeframe set {sorted(timeframes)}"
        )

    ohlc_errors: list[dict[str, Any]] = []
    for row in rows:
        if row.low > row.high:
            ohlc_errors.append(
                {
                    "index": row.index,
                    "reason": "low_above_high",
                }
            )
        if row.high < max(row.open, row.close) or row.low > min(
            row.open, row.close
        ):
            ohlc_errors.append(
                {
                    "index": row.index,
                    "reason": "inconsistent_ohlc",
                }
            )
        if row.spread < 0:
            ohlc_errors.append(
                {
                    "index": row.index,
                    "reason": "negative_spread",
                }
            )

    if ohlc_errors:
        raise HoldoutError(
            f"REFUSED: {len(ohlc_errors)} OHLC consistency errors"
        )

    by_ts: dict[str, list[RawRow]] = {}
    for row in rows:
        by_ts.setdefault(row.timestamp_raw, []).append(row)

    duplicate_timestamps = {
        ts: len(group)
        for ts, group in by_ts.items()
        if len(group) > 1
    }
    conflicting = []
    exact_duplicate_rows = 0
    for ts, group in by_ts.items():
        if len(group) < 2:
            continue
        signatures = {
            (
                row.open,
                row.high,
                row.low,
                row.close,
                row.tick_volume,
                row.volume,
                row.spread,
                row.symbol,
                row.timeframe,
            )
            for row in group
        }
        if len(signatures) > 1:
            conflicting.append(ts)
        else:
            exact_duplicate_rows += len(group) - 1

    if conflicting:
        raise HoldoutError(
            "REFUSED: conflicting duplicate timestamps: "
            + ", ".join(conflicting[:5])
        )
    if duplicate_timestamps:
        raise HoldoutError(
            "REFUSED: duplicate timestamps present "
            f"({len(duplicate_timestamps)} keys)"
        )

    for previous, current in zip(rows, rows[1:]):
        if current.timestamp_naive <= previous.timestamp_naive:
            raise HoldoutError(
                "REFUSED: timestamps are not strictly increasing at "
                f"index {current.index}"
            )

    gaps_hours: Counter[int] = Counter()
    multi_hour_gaps: list[dict[str, Any]] = []
    for previous, current in zip(rows, rows[1:]):
        delta_hours = int(
            (
                current.timestamp_naive - previous.timestamp_naive
            ).total_seconds()
            // 3600
        )
        gaps_hours[delta_hours] += 1
        if delta_hours > 1:
            multi_hour_gaps.append(
                {
                    "from_index": previous.index,
                    "to_index": current.index,
                    "from_timestamp": previous.timestamp_raw,
                    "to_timestamp": current.timestamp_raw,
                    "gap_hours": delta_hours,
                }
            )

    return {
        "row_count": len(rows),
        "symbol": "XAUUSD.vx",
        "timeframe": "PERIOD_H1",
        "first_server_timestamp": rows[0].timestamp_raw,
        "last_server_timestamp": rows[-1].timestamp_raw,
        "duplicate_timestamp_keys": 0,
        "exact_duplicate_rows": exact_duplicate_rows,
        "conflicting_duplicate_timestamps": [],
        "ohlc_errors": ohlc_errors,
        "gap_hours_histogram": {
            str(k): gaps_hours[k] for k in sorted(gaps_hours)
        },
        "multi_hour_gap_count": len(multi_hour_gaps),
        "multi_hour_gaps_sample": multi_hour_gaps[:20],
    }


def load_canonical_overlap(path: Path) -> list[dict[str, Any]]:
    import gzip

    rows: list[dict[str, Any]] = []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(
                {
                    "timestamp_utc": parse_utc(row["timestamp_utc"]),
                    "open": dec(row["open"]),
                    "high": dec(row["high"]),
                    "low": dec(row["low"]),
                    "close": dec(row["close"]),
                    "tick_volume": int(row["tick_volume"]),
                    "volume": int(row["volume"]),
                    "mean_spread": (
                        None
                        if row.get("mean_spread", "") == ""
                        else dec(row["mean_spread"])
                    ),
                }
            )
    if not rows:
        raise HoldoutError("REFUSED: empty canonical overlap file")
    return rows


def validate_timezone_model(
    raw_rows: list[RawRow],
    canonical_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate an EET/EEST-compatible schedule without unique IANA attribution.

    Multiple IANA zones may reproduce the exposed canonical overlap exactly.
    That is recorded as a non-unique offset schedule. Europe/Athens is kept only
    as a deterministic conversion reference, not as the broker's identified zone.
    """
    evidence: list[dict[str, Any]] = []
    exact_matches: list[str] = []

    for tz_name in PREFERRED_TIMEZONES:
        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            evidence.append(
                {
                    "timezone": tz_name,
                    "status": "UNAVAILABLE",
                }
            )
            continue

        by_utc: dict[datetime, RawRow] = {}
        conflict = False
        for row in raw_rows:
            localized = row.timestamp_naive.replace(tzinfo=tz)
            utc = localized.astimezone(timezone.utc)
            if utc in by_utc:
                conflict = True
                break
            by_utc[utc] = row

        if conflict:
            evidence.append(
                {
                    "timezone": tz_name,
                    "status": "UTC_COLLISION",
                }
            )
            continue

        missing = 0
        ohlc_mismatch = 0
        offsets: set[float] = set()
        dst_transitions: list[dict[str, Any]] = []
        previous_offset = None
        first_match = None
        last_match = None

        for canon in canonical_rows:
            hit = by_utc.get(canon["timestamp_utc"])
            if hit is None:
                missing += 1
                continue
            if (
                hit.open != canon["open"]
                or hit.high != canon["high"]
                or hit.low != canon["low"]
                or hit.close != canon["close"]
            ):
                ohlc_mismatch += 1
                continue

            localized = hit.timestamp_naive.replace(tzinfo=tz)
            offset_hours = (
                localized.utcoffset().total_seconds() / 3600.0
            )
            offsets.add(offset_hours)
            if (
                previous_offset is not None
                and offset_hours != previous_offset
            ):
                dst_transitions.append(
                    {
                        "server_timestamp": hit.timestamp_raw,
                        "from_offset_hours": previous_offset,
                        "to_offset_hours": offset_hours,
                        "utc": utc_text(canon["timestamp_utc"]),
                    }
                )
            previous_offset = offset_hours
            if first_match is None:
                first_match = {
                    "raw_index": hit.index,
                    "server_timestamp": hit.timestamp_raw,
                    "utc": utc_text(canon["timestamp_utc"]),
                    "open": str(hit.open),
                    "high": str(hit.high),
                    "low": str(hit.low),
                    "close": str(hit.close),
                }
            last_match = {
                "raw_index": hit.index,
                "server_timestamp": hit.timestamp_raw,
                "utc": utc_text(canon["timestamp_utc"]),
                "open": str(hit.open),
                "high": str(hit.high),
                "low": str(hit.low),
                "close": str(hit.close),
            }

        timestamp_matches = len(canonical_rows) - missing
        ohlc_matches = timestamp_matches - ohlc_mismatch
        status = (
            "EXACT_MATCH"
            if missing == 0 and ohlc_mismatch == 0
            else "MISMATCH"
        )
        item = {
            "timezone": tz_name,
            "status": status,
            "canonical_rows": len(canonical_rows),
            "canonical_timestamp_matches": timestamp_matches,
            "canonical_ohlc_matches": ohlc_matches,
            "exact_ohlc_matches": ohlc_matches,
            "missing_utc": missing,
            "ohlc_mismatches": ohlc_mismatch,
            "offsets_hours_observed": sorted(offsets),
            "winter_utc_plus_2_observed": 2.0 in offsets,
            "summer_utc_plus_3_observed": 3.0 in offsets,
            "dst_transition_count_in_overlap": len(dst_transitions),
            "dst_transitions": dst_transitions,
            "first_exact_overlap": first_match,
            "last_exact_overlap": last_match,
        }
        evidence.append(item)
        if status == "EXACT_MATCH":
            exact_matches.append(tz_name)

    if not exact_matches:
        raise HoldoutError(
            "REFUSED: no named timezone reproduced the canonical overlap "
            "exactly; refusing piecewise offset guessing"
        )

    if CONVERSION_REFERENCE_TIMEZONE not in exact_matches:
        raise HoldoutError(
            "REFUSED: conversion reference timezone "
            f"{CONVERSION_REFERENCE_TIMEZONE} did not reproduce the "
            "canonical overlap exactly"
        )

    if len(exact_matches) < 2:
        raise HoldoutError(
            "REFUSED: only one candidate IANA zone matched the overlap; "
            "cannot classify a non-unique EET/EEST-equivalent schedule"
        )

    reference_evidence = next(
        item
        for item in evidence
        if item["timezone"] == CONVERSION_REFERENCE_TIMEZONE
    )

    if not (
        reference_evidence["winter_utc_plus_2_observed"]
        and reference_evidence["summer_utc_plus_3_observed"]
    ):
        raise HoldoutError(
            "REFUSED: EET/EEST schedule did not exhibit both winter UTC+2 "
            "and summer UTC+3 within the overlap"
        )

    if reference_evidence["dst_transition_count_in_overlap"] < 1:
        raise HoldoutError(
            "REFUSED: EET/EEST schedule showed no DST transitions in overlap"
        )

    # Confirm every exact-match zone observed the same offset set on overlap.
    reference_offsets = reference_evidence["offsets_hours_observed"]
    for tz_name in exact_matches:
        item = next(e for e in evidence if e["timezone"] == tz_name)
        if item["offsets_hours_observed"] != reference_offsets:
            raise HoldoutError(
                "REFUSED: exact-match timezones observed divergent offsets "
                f"on overlap ({tz_name})"
            )

    return {
        "classification": TIMEZONE_SCHEDULE_CLASSIFICATION,
        "exact_iana_zone_identified": False,
        "conversion_reference_timezone": CONVERSION_REFERENCE_TIMEZONE,
        "conversion_reference_role": (
            "DETERMINISTIC_IMPLEMENTATION_REFERENCE_ONLY"
        ),
        "equivalent_exact_match_timezones": exact_matches,
        "offsets_hours_observed": reference_offsets,
        "winter_utc_plus_2_observed": True,
        "summer_utc_plus_3_observed": True,
        "overlap_count": len(canonical_rows),
        "canonical_timestamp_matches": len(canonical_rows),
        "canonical_ohlc_matches": len(canonical_rows),
        "attribution_notes": [
            (
                "The exact broker IANA timezone cannot be uniquely "
                "attributed."
            ),
            (
                "The data follows an EET/EEST-compatible UTC+2 winter / "
                "UTC+3 summer schedule."
            ),
            (
                f"{CONVERSION_REFERENCE_TIMEZONE} is used only as a "
                "deterministic conversion reference."
            ),
            (
                "Helsinki and Bucharest produce identical conversions for "
                "the validated period."
            ),
            (
                "This is not evidence that the broker server is physically "
                "or administratively located in Athens."
            ),
        ],
        "method": (
            "Interpret naive MT5 server timestamps with each candidate IANA "
            "zone and require exact UTC timestamp + Decimal OHLC equality "
            "against every exposed canonical row. When multiple EET/EEST "
            "zones match, record a non-unique offset schedule and keep "
            f"{CONVERSION_REFERENCE_TIMEZONE} only as an implementation "
            "reference. No fixed-offset shortcut."
        ),
        "validation_evidence": evidence,
        "first_exact_overlap": reference_evidence["first_exact_overlap"],
        "last_exact_overlap": reference_evidence["last_exact_overlap"],
    }


def assert_retrospective_timezone_equivalence(
    rows: list[RawRow],
    timezones: list[str],
    *,
    conversion_reference_timezone: str = CONVERSION_REFERENCE_TIMEZONE,
) -> dict[str, Any]:
    """Require identical UTC conversions across candidate zones on holdout rows."""
    if len(timezones) < 2:
        raise HoldoutError(
            "REFUSED: retrospective timezone equivalence requires at least "
            "two candidate zones"
        )
    if conversion_reference_timezone not in timezones:
        raise HoldoutError(
            "REFUSED: conversion reference timezone missing from equivalence "
            "candidate set"
        )
    if not rows:
        raise HoldoutError(
            "REFUSED: no retrospective rows available for timezone equivalence"
        )

    zone_objects: dict[str, ZoneInfo] = {}
    for name in timezones:
        try:
            zone_objects[name] = ZoneInfo(name)
        except ZoneInfoNotFoundError as exc:
            raise HoldoutError(
                f"REFUSED: unavailable timezone during equivalence check: {name}"
            ) from exc

    reference_tz = zone_objects[conversion_reference_timezone]
    first_divergence: dict[str, Any] | None = None

    for row in rows:
        reference_utc = row.timestamp_naive.replace(
            tzinfo=reference_tz
        ).astimezone(timezone.utc)
        for name, tz in zone_objects.items():
            if name == conversion_reference_timezone:
                continue
            other_utc = row.timestamp_naive.replace(tzinfo=tz).astimezone(
                timezone.utc
            )
            if other_utc != reference_utc:
                first_divergence = {
                    "raw_index": row.index,
                    "server_timestamp": row.timestamp_raw,
                    "conversion_reference_timezone": (
                        conversion_reference_timezone
                    ),
                    "conversion_reference_utc": utc_text(reference_utc),
                    "divergent_timezone": name,
                    "divergent_utc": utc_text(other_utc),
                }
                break
        if first_divergence is not None:
            break

    if first_divergence is not None:
        raise HoldoutError(
            "REFUSED: candidate timezones diverge on retrospective rows: "
            + json.dumps(first_divergence, sort_keys=True)
        )

    return {
        "retrospective_rows_checked": len(rows),
        "retrospective_equivalent_utc_conversions": True,
        "retrospective_timezone_equivalence_passed": True,
        "equivalence_start_server_timestamp": rows[0].timestamp_raw,
        "equivalence_end_server_timestamp": rows[-1].timestamp_raw,
        "equivalence_timezones": list(timezones),
        "conversion_reference_timezone": conversion_reference_timezone,
    }


def localize_rows(
    raw_rows: list[RawRow],
    timezone_name: str,
) -> list[tuple[RawRow, datetime]]:
    tz = ZoneInfo(timezone_name)
    localized: list[tuple[RawRow, datetime]] = []
    seen: set[datetime] = set()
    for row in raw_rows:
        utc = row.timestamp_naive.replace(tzinfo=tz).astimezone(
            timezone.utc
        )
        if utc in seen:
            raise HoldoutError(
                f"REFUSED: localized UTC collision at {utc.isoformat()}"
            )
        seen.add(utc)
        localized.append((row, utc))
    return localized


def compute_holdout_boundary(
    localized: list[tuple[RawRow, datetime]],
    first_overlap: dict[str, Any],
) -> dict[str, Any]:
    exposed_index = int(first_overlap["raw_index"])
    if localized[exposed_index][0].index != exposed_index:
        raise HoldoutError(
            "REFUSED: exposed boundary index mismatch"
        )

    holdout_end_exclusive = exposed_index - EMBARGO_BARS
    if holdout_end_exclusive <= 0:
        raise HoldoutError(
            "REFUSED: 48-bar embargo leaves insufficient retrospective data"
        )

    # Minimum usable bars after later window guards (48+48) and 6*192 windows.
    minimum_for_windows = 48 + 48 + (6 * 192)
    if holdout_end_exclusive < minimum_for_windows:
        raise HoldoutError(
            "REFUSED: retrospective prefix too short for price-blind windows "
            f"({holdout_end_exclusive} < {minimum_for_windows})"
        )

    holdout = localized[:holdout_end_exclusive]
    return {
        "exposed_boundary_raw_index": exposed_index,
        "exposed_boundary_server_timestamp": first_overlap[
            "server_timestamp"
        ],
        "exposed_boundary_utc": first_overlap["utc"],
        "embargo_bars": EMBARGO_BARS,
        "holdout_end_exclusive": holdout_end_exclusive,
        "retrospective_row_count": len(holdout),
        "retrospective_first_server_timestamp": holdout[0][
            0
        ].timestamp_raw,
        "retrospective_last_server_timestamp": holdout[-1][
            0
        ].timestamp_raw,
        "retrospective_first_utc": utc_text(holdout[0][1]),
        "retrospective_last_utc": utc_text(holdout[-1][1]),
        "embargo_server_range": {
            "start_index": holdout_end_exclusive,
            "end_index_exclusive": exposed_index,
            "first_server_timestamp": localized[holdout_end_exclusive][
                0
            ].timestamp_raw,
            "last_server_timestamp": localized[exposed_index - 1][
                0
            ].timestamp_raw,
            "first_utc": utc_text(localized[holdout_end_exclusive][1]),
            "last_utc": utc_text(localized[exposed_index - 1][1]),
        },
    }


def load_manifest_intervals() -> list[dict[str, Any]]:
    manifests = [
        ROOT
        / "benchmarks"
        / "datasets"
        / "XAUUSD_H1.human.manifest.json",
        ROOT
        / "benchmarks"
        / "datasets"
        / "XAUUSD_H1_2026H1.human.manifest.json",
    ]
    intervals: list[dict[str, Any]] = []
    for path in manifests:
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        data_files = {
            item.get("data_file")
            for item in payload.get("datasets", [])
            if item.get("data_file")
        }
        for data_file in sorted(x for x in data_files if x):
            full = ROOT / "benchmarks" / data_file
            if not full.exists():
                # Some manifests store paths relative to benchmarks/
                alt = ROOT / data_file
                full = alt if alt.exists() else full
            if not full.exists():
                raise HoldoutError(
                    f"REFUSED: manifest data file missing: {data_file}"
                )
            import gzip

            with gzip.open(
                full, "rt", encoding="utf-8", newline=""
            ) as handle:
                reader = csv.DictReader(handle)
                timestamps = [
                    parse_utc(row["timestamp_utc"]) for row in reader
                ]
            if not timestamps:
                continue
            intervals.append(
                {
                    "manifest": display_path(path),
                    "data_file": data_file,
                    "first_utc": utc_text(timestamps[0]),
                    "last_utc": utc_text(timestamps[-1]),
                    "bar_count": len(timestamps),
                }
            )
    return intervals


def assert_no_manifest_overlap(
    holdout_first: datetime,
    holdout_last: datetime,
    intervals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    overlaps = []
    for interval in intervals:
        start = parse_utc(interval["first_utc"])
        end = parse_utc(interval["last_utc"])
        if holdout_last >= start and holdout_first <= end:
            overlaps.append(interval)
    if overlaps:
        raise HoldoutError(
            "REFUSED: retrospective interval overlaps exposed manifest data: "
            + json.dumps(overlaps)
        )
    return intervals


def assert_no_quarantine_overlap(
    holdout_last: datetime,
) -> dict[str, Any]:
    quarantine_root = (
        ROOT
        / "benchmarks"
        / "data"
        / "quarantine"
        / "XAUUSD"
        / "H1"
        / "post_2026H1"
    )
    if not quarantine_root.exists():
        return {
            "present": False,
            "note": "No post-2026H1 quarantine directory present",
        }

    # Quarantine is post-2026 by construction; still fail if any UTC <= holdout.
    earliest = None
    for meta in quarantine_root.glob("*/snapshot_manifest.json"):
        payload = json.loads(meta.read_text(encoding="utf-8"))
        for key in (
            "first_normalized_utc",
            "first_utc",
            "coverage_first_utc",
        ):
            if key in payload:
                ts = parse_utc(str(payload[key]))
                if earliest is None or ts < earliest:
                    earliest = ts
    if earliest is not None and earliest <= holdout_last:
        raise HoldoutError(
            "REFUSED: quarantine coverage overlaps retrospective holdout"
        )
    return {
        "present": True,
        "path": display_path(quarantine_root),
        "earliest_observed_utc": (
            None if earliest is None else utc_text(earliest)
        ),
        "overlaps_retrospective": False,
    }


def build_candles(
    holdout: list[tuple[RawRow, datetime]],
) -> list[Candle]:
    candles: list[Candle] = []
    for row, ts in holdout:
        candles.append(
            Candle(
                symbol="XAUUSD",
                timeframe=Timeframe.H1,
                timestamp=ts,
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=row.volume,
                tick_volume=row.tick_volume,
                spread=float(row.spread),
            )
        )
    return candles


def build_protocol() -> dict[str, Any]:
    return {
        "protocol_id": PROTOCOL_ID,
        "frozen_on": "2026-07-21",
        "benchmark_type": CLASSIFICATION,
        "classification_notes": [
            "The source existed before benchmark construction.",
            "This is not a prospective forward test.",
            (
                "It is useful for independent chronological stress testing "
                "only if its selected interval was not used in prior tuning "
                "or evaluation."
            ),
            (
                "Passing this benchmark may support an interim engineering "
                "decision."
            ),
            (
                "It cannot replace the frozen post-2026H1 final certification."
            ),
        ],
        "candidate": {
            "version": "2.3.0-rc1",
            "commit": "3fd5d7c74b82c3728d7badaa6cd72044bdd6bd1d",
        },
        "baseline": {
            "version": "2.2.0",
        },
        "split": "TEST",
        "tuning_allowed": False,
        "source": {
            "package_status": PACKAGE_STATUS,
            "eligible_for_tuning": False,
            "eligible_for_labeling": True,
            "eligible_for_evaluation": False,
            "prospective_test": False,
            "embargo_bars_before_exposed_boundary": EMBARGO_BARS,
        },
        "window_selection": {
            "selection_uses_prices_or_predictions": False,
            "leading_guard_bars": 48,
            "trailing_guard_bars": 48,
            "bucket_count": 6,
            "window_bars": 192,
            "algorithm_version": "PRICE_BLIND_SIX_BUCKET_CENTERED_V1",
            "algorithm": [
                "Sort frozen canonical bars chronologically.",
                "Exclude 48 leading and 48 trailing bars.",
                "Divide remaining eligible indices into six equal chronological buckets.",
                "Select one centered contiguous 192-bar window per bucket.",
                "Require six non-overlapping windows.",
                "Fail rather than shift, resize, or cherry-pick windows.",
                "Do not inspect OHLC, volatility, labels, predictions, or engine output.",
            ],
        },
        "labeling": {
            "predictions_visible_during_labeling": False,
            "engine_version_visible_during_labeling": False,
            "passes": 2,
            "minimum_days_between_passes": 3,
            "conflicts_require_explicit_adjudication": True,
            "automatic_conflict_resolution": False,
            "bars_and_labels_frozen_before_evaluation": True,
            "allowed_adjudication_decisions": [
                "PASS_1",
                "PASS_2",
                "CUSTOM",
                "EXCLUDE",
            ],
            "nonempty_notes_required_for_every_adjudication": True,
        },
        "evaluation": {
            "candidate_evaluations_allowed": 1,
            "baseline_evaluations_allowed": 1,
            "error_analysis_before_release_decision": False,
            "tuning_after_unblinding": False,
            "prefix_stability_required": True,
            "final_production_certification_requires": (
                "prospective post-2026H1 locked benchmark"
            ),
        },
        "engineering_gates": {
            "prefix_stability_failures_max": 0,
            "location_precision_min": 0.80,
            "location_recall_min": 0.70,
            "location_f1_min": 0.75,
            "semantic_f1_min": 0.60,
            "major_external_precision_min": 0.85,
            "major_external_recall_min": 0.40,
            "worst_window_location_f1_min": 0.50,
            "candidate_location_f1_delta_vs_v2_2_min": 0.00,
            "candidate_semantic_f1_delta_vs_v2_2_min": 0.00,
        },
        "decision_values": [
            "PASS_RETROSPECTIVE_ENGINEERING_GATE",
            "FAIL_RETROSPECTIVE_ENGINEERING_GATE",
        ],
        "forbidden_decision_values": [
            "PROMOTE_V2_3_0_FINAL",
        ],
        "current_status": "SOURCE_PROTOCOL_DEFINED_AWAITING_WINDOW_SELECTION",
    }


def write_readme(path: Path, audit: dict[str, Any]) -> None:
    boundary = audit["holdout_boundary"]
    tz = audit["timezone_model"]
    text = f"""# XAUUSD H1 2022–2024 Retrospective Holdout Source

**Classification:** `{CLASSIFICATION}`

**Package status:** `{PACKAGE_STATUS}`

## What this is

A contamination-aware retrospective holdout built from the chronological
prefix of the full MT5 `FXNavigators_XAUUSD_H1.csv` history ending strictly
before the already-exposed canonical 2024-07-15 boundary, plus a
{EMBARGO_BARS}-bar embargo.

## What this is not

- Not a prospective forward test.
- Not a replacement for the frozen post-2026H1 final certification.
- Not eligible for tuning.
- Not eligible for evaluation until human-adjudicated labels are frozen.

## Coverage

- Retrospective rows: `{boundary["retrospective_row_count"]}`
- First UTC: `{boundary["retrospective_first_utc"]}`
- Last UTC: `{boundary["retrospective_last_utc"]}`
- Timezone schedule: `{tz["classification"]}`
- Exact IANA zone identified: `{tz["exact_iana_zone_identified"]}`
- Conversion reference (implementation only): `{tz["conversion_reference_timezone"]}`
- Equivalent exact-match zones: `{", ".join(tz["equivalent_exact_match_timezones"])}`
- Exposed boundary raw index: `{boundary["exposed_boundary_raw_index"]}`
- Embargo bars: `{boundary["embargo_bars"]}`

## Timezone attribution honesty

- The exact broker IANA timezone cannot be uniquely attributed.
- The data follows an EET/EEST-compatible UTC+2 winter / UTC+3 summer schedule.
- `{tz["conversion_reference_timezone"]}` is used only as a deterministic
  conversion reference (`{tz["conversion_reference_role"]}`).
- Helsinki and Bucharest produce identical conversions for the validated
  period.
- This is not evidence that the broker server is physically or
  administratively located in Athens.

## Eligibility flags

- `eligible_for_tuning`: false
- `eligible_for_labeling`: true
- `eligible_for_evaluation`: false
- `prospective_test`: false

## Contamination honesty

The source existed before this package was constructed. Passing a later
retrospective evaluation may support an interim engineering decision only.
Final production certification still requires the prospective post-2026H1
benchmark.
"""
    path.write_text(text, encoding="utf-8")


def atomic_publish(staging: Path, output_root: Path) -> None:
    output_root.parent.mkdir(parents=True, exist_ok=True)
    if output_root.exists():
        raise HoldoutError(
            f"REFUSED: output package already exists: {output_root}"
        )
    os.rename(staging, output_root)


def main() -> int:
    args = parse_args()
    raw_path = args.raw.expanduser().resolve()
    overlap_path = args.canonical_overlap.expanduser().resolve()
    duplicate_path = args.duplicate_copy.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    protocol_output = args.protocol_output.expanduser().resolve()

    if not raw_path.exists():
        raise HoldoutError(f"REFUSED: missing raw source {raw_path}")
    if not overlap_path.exists():
        raise HoldoutError(
            f"REFUSED: missing canonical overlap {overlap_path}"
        )

    provenance = provenance_audit(duplicate_path)

    raw_rows, raw_bytes, _header = load_raw_rows(raw_path)
    raw_sha = sha256_bytes(raw_bytes)
    if len(raw_rows) != EXPECTED_ROW_COUNT:
        # load_raw_rows already checks, keep explicit.
        pass

    duplicate_sha = None
    duplicate_identical = None
    if duplicate_path.exists():
        duplicate_sha = sha256_file(duplicate_path)
        duplicate_identical = duplicate_sha == raw_sha
        if not duplicate_identical:
            raise HoldoutError(
                "REFUSED: raw source and chart_csv duplicate are not "
                "byte-identical"
            )
    else:
        raise HoldoutError(
            "REFUSED: expected tracked duplicate copy missing: "
            f"{duplicate_path}"
        )

    integrity = validate_raw_identity(raw_rows)
    if integrity["row_count"] != EXPECTED_ROW_COUNT:
        raise HoldoutError("REFUSED: unexpected row count after validation")

    expected_sha = (
        "fe8a7f95c7d2b90cef759a7e23b11679b7f84e4928fb2fd67111fe89fb318d4c"
    )
    if raw_sha != expected_sha:
        raise HoldoutError(
            "REFUSED: raw SHA-256 mismatch: "
            f"got {raw_sha}, expected {expected_sha}"
        )

    canonical_rows = load_canonical_overlap(overlap_path)
    canonical_sha = sha256_file(overlap_path)
    timezone_model = validate_timezone_model(raw_rows, canonical_rows)
    localized = localize_rows(
        raw_rows,
        timezone_model["conversion_reference_timezone"],
    )
    boundary = compute_holdout_boundary(
        localized,
        timezone_model["first_exact_overlap"],
    )
    holdout = localized[: boundary["holdout_end_exclusive"]]
    holdout_raw_rows = [row for row, _ts in holdout]
    equivalence = assert_retrospective_timezone_equivalence(
        holdout_raw_rows,
        timezone_model["equivalent_exact_match_timezones"],
        conversion_reference_timezone=timezone_model[
            "conversion_reference_timezone"
        ],
    )
    timezone_model["retrospective_equivalence"] = equivalence

    intervals = load_manifest_intervals()
    assert_no_manifest_overlap(
        parse_utc(boundary["retrospective_first_utc"]),
        parse_utc(boundary["retrospective_last_utc"]),
        intervals,
    )
    quarantine = assert_no_quarantine_overlap(
        parse_utc(boundary["retrospective_last_utc"])
    )

    audit: dict[str, Any] = {
        "classification": CLASSIFICATION,
        "package_status": PACKAGE_STATUS,
        "source_hashes": {
            "raw_sha256": raw_sha,
            "duplicate_copy_sha256": duplicate_sha,
            "canonical_overlap_sha256": canonical_sha,
            "raw_path": display_path(raw_path)
            if raw_path.is_relative_to(ROOT)
            else str(raw_path),
            "duplicate_copy_path": display_path(duplicate_path),
            "canonical_overlap_path": display_path(overlap_path),
            "raw_and_duplicate_byte_identical": duplicate_identical,
        },
        "provenance_findings": provenance,
        "raw_coverage": {
            "row_count": integrity["row_count"],
            "first_server_timestamp": integrity[
                "first_server_timestamp"
            ],
            "last_server_timestamp": integrity["last_server_timestamp"],
            "symbol": integrity["symbol"],
            "timeframe": integrity["timeframe"],
        },
        "integrity": integrity,
        "timezone_model": timezone_model,
        "timezone_validation_evidence": timezone_model[
            "validation_evidence"
        ],
        "retrospective_timezone_equivalence": equivalence,
        "overlap_counts": {
            "canonical_rows": len(canonical_rows),
            "canonical_timestamp_matches": timezone_model[
                "canonical_timestamp_matches"
            ],
            "canonical_ohlc_matches": timezone_model[
                "canonical_ohlc_matches"
            ],
        },
        "first_exact_overlap": timezone_model["first_exact_overlap"],
        "last_exact_overlap": timezone_model["last_exact_overlap"],
        "exposed_boundary_raw_index": boundary[
            "exposed_boundary_raw_index"
        ],
        "embargo_bars": boundary["embargo_bars"],
        "holdout_boundary": boundary,
        "retrospective_row_count": boundary["retrospective_row_count"],
        "retrospective_utc_coverage": {
            "first_utc": boundary["retrospective_first_utc"],
            "last_utc": boundary["retrospective_last_utc"],
        },
        "duplicate_count": integrity["exact_duplicate_rows"],
        "ohlc_errors": integrity["ohlc_errors"],
        "gap_distribution": integrity["gap_hours_histogram"],
        "exposed_manifest_intervals": intervals,
        "quarantine_check": quarantine,
        "contamination_caveats": provenance["caveats"],
        "eligibility": {
            "eligible_for_tuning": False,
            "eligible_for_labeling": True,
            "eligible_for_evaluation": False,
            "prospective_test": False,
        },
        "labels_loaded": False,
        "predictions_loaded": False,
        "swing_engine_executed": False,
        "candidate_evaluated": False,
        "baseline_evaluated": False,
    }

    if args.audit_only:
        audit_path = (
            args.audit_output.expanduser().resolve()
            if args.audit_output
            else (Path.cwd() / "retrospective_holdout_audit.json")
        )
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(
            json.dumps(audit, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Audit only: {audit_path}")
        print(f"Retrospective rows: {boundary['retrospective_row_count']}")
        print(
            "UTC coverage: "
            f"{boundary['retrospective_first_utc']} .. "
            f"{boundary['retrospective_last_utc']}"
        )
        return 0

    if output_root.exists():
        raise HoldoutError(
            f"REFUSED: output package already exists: {output_root}"
        )
    if protocol_output.exists():
        raise HoldoutError(
            f"REFUSED: protocol already exists: {protocol_output}"
        )

    staging_parent = output_root.parent
    staging_parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=".H1_2022_2024_v1_staging_",
            dir=str(staging_parent),
        )
    )

    try:
        # Exact raw prefix bytes: header + selected line bytes.
        raw_out = staging / RAW_OUT_NAME
        with raw_out.open("wb") as handle:
            # Preserve UTF-8-SIG BOM if present on source header.
            source_lines = raw_bytes.split(b"\r\n")
            if source_lines and source_lines[-1] == b"":
                source_lines = source_lines[:-1]
            handle.write(source_lines[0] + b"\r\n")
            for row, _ts in holdout:
                handle.write(row.line_bytes)

        candles = build_candles(holdout)
        canonical_out = staging / CANONICAL_OUT_NAME
        write_canonical_candles_csv(
            canonical_out,
            candles,
            source=SOURCE_ID,
            price_basis=PRICE_BASIS,
        )

        raw_out_sha = sha256_file(raw_out)
        canonical_out_sha = sha256_file(canonical_out)

        # Determinism check: rewrite once to a temp file and compare hash.
        verify_path = staging / ".canonical_verify.csv.gz"
        write_canonical_candles_csv(
            verify_path,
            candles,
            source=SOURCE_ID,
            price_basis=PRICE_BASIS,
        )
        verify_sha = sha256_file(verify_path)
        verify_path.unlink()
        if verify_sha != canonical_out_sha:
            raise HoldoutError(
                "REFUSED: canonical gzip output was not deterministic"
            )

        audit["output_hashes"] = {
            RAW_OUT_NAME: raw_out_sha,
            CANONICAL_OUT_NAME: canonical_out_sha,
        }
        audit["package_status"] = PACKAGE_STATUS

        audit_out = staging / AUDIT_OUT_NAME
        audit_out.write_text(
            json.dumps(audit, indent=2) + "\n",
            encoding="utf-8",
        )
        audit_sha = sha256_file(audit_out)

        manifest = {
            "package_id": "XAUUSD_H1_2022_2024_RETROSPECTIVE_HOLDOUT_V1",
            "classification": CLASSIFICATION,
            "status": PACKAGE_STATUS,
            "symbol": "XAUUSD",
            "timeframe": "H1",
            "source": SOURCE_ID,
            "price_basis": PRICE_BASIS,
            "timezone_schedule": {
                "classification": timezone_model["classification"],
                "exact_iana_zone_identified": False,
                "conversion_reference_timezone": timezone_model[
                    "conversion_reference_timezone"
                ],
                "conversion_reference_role": timezone_model[
                    "conversion_reference_role"
                ],
                "equivalent_exact_match_timezones": timezone_model[
                    "equivalent_exact_match_timezones"
                ],
                "offsets_hours_observed": timezone_model[
                    "offsets_hours_observed"
                ],
                "attribution_notes": timezone_model["attribution_notes"],
            },
            "row_count": boundary["retrospective_row_count"],
            "first_utc": boundary["retrospective_first_utc"],
            "last_utc": boundary["retrospective_last_utc"],
            "embargo_bars": EMBARGO_BARS,
            "exposed_boundary_raw_index": boundary[
                "exposed_boundary_raw_index"
            ],
            "files": {
                RAW_OUT_NAME: raw_out_sha,
                CANONICAL_OUT_NAME: canonical_out_sha,
                AUDIT_OUT_NAME: audit_sha,
            },
            "eligibility": audit["eligibility"],
            "labels_loaded": False,
            "predictions_loaded": False,
            "swing_engine_executed": False,
            "candidate_evaluated": False,
            "baseline_evaluated": False,
        }
        manifest_out = staging / MANIFEST_OUT_NAME
        manifest_out.write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )
        manifest["files"][MANIFEST_OUT_NAME] = sha256_file(manifest_out)
        # Rewrite manifest including its own hash placeholder carefully:
        # store sidecar hashes without self-hash recursion; keep file hashes
        # for the other artifacts only.
        manifest_out.write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )

        write_readme(staging / README_OUT_NAME, audit)

        protocol = build_protocol()
        protocol["source_package"] = {
            "path": display_path(output_root),
            "canonical_file": CANONICAL_OUT_NAME,
            "canonical_sha256": canonical_out_sha,
            "raw_file": RAW_OUT_NAME,
            "raw_sha256": raw_out_sha,
            "row_count": boundary["retrospective_row_count"],
            "first_utc": boundary["retrospective_first_utc"],
            "last_utc": boundary["retrospective_last_utc"],
        }

        protocol_staging = Path(
            tempfile.mkdtemp(
                prefix=".protocol_staging_",
                dir=str(protocol_output.parent),
            )
        )
        try:
            protocol_tmp = (
                protocol_staging
                / protocol_output.name
            )
            protocol_tmp.write_text(
                json.dumps(protocol, indent=2) + "\n",
                encoding="utf-8",
            )
            atomic_publish(staging, output_root)
            protocol_output.parent.mkdir(parents=True, exist_ok=True)
            os.rename(protocol_tmp, protocol_output)
        finally:
            if protocol_staging.exists():
                shutil.rmtree(protocol_staging, ignore_errors=True)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    print(f"Published package: {display_path(output_root)}")
    print(f"Published protocol: {display_path(protocol_output)}")
    print(f"Raw SHA-256: {raw_sha}")
    print(f"Canonical SHA-256: {canonical_out_sha}")
    print(f"Retrospective rows: {boundary['retrospective_row_count']}")
    print(
        "UTC coverage: "
        f"{boundary['retrospective_first_utc']} .. "
        f"{boundary['retrospective_last_utc']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

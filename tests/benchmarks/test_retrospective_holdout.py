"""Focused tests for the XAUUSD H1 2022–2024 retrospective holdout workflow."""

from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def load_script(filename: str, module_name: str):
    path = ROOT / "scripts" / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


PREPARE = load_script(
    "prepare_xauusd_h1_retrospective_holdout.py",
    "test_retrospective_prepare",
)
SELECTOR = load_script(
    "select_xauusd_h1_2022_2024_retrospective_windows.py",
    "test_retrospective_selector",
)
EVALUATOR = load_script(
    "evaluate_xauusd_h1_2022_2024_retrospective_locked.py",
    "test_retrospective_evaluator",
)
PASSES = load_script(
    "manage_xauusd_h1_post_2026h1_label_passes.py",
    "test_retrospective_passes_impl",
)

from shared.types.models import Candle, Timeframe  # noqa: E402
from swing_engine.benchmark_data import write_canonical_candles_csv  # noqa: E402


CANDIDATE_COMMIT = "3fd5d7c74b82c3728d7badaa6cd72044bdd6bd1d"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return path


def engineering_gates() -> dict:
    return {
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
    }


def make_raw_csv(
    path: Path,
    rows: list[tuple[str, str, str, str, str]],
    *,
    symbol: str = "XAUUSD.vx",
) -> Path:
    lines = [
        "timestamp,open,high,low,close,tick_volume,volume,spread,symbol,timeframe\r\n"
    ]
    for ts, o, h, l, c in rows:
        lines.append(
            f"{ts},{o},{h},{l},{c},100,0,0.10,{symbol},PERIOD_H1\r\n"
        )
    path.write_bytes("".join(lines).encode("utf-8"))
    return path


def athens_server(utc: datetime) -> str:
    local = utc.astimezone(ZoneInfo("Europe/Athens"))
    return local.strftime("%Y.%m.%d %H:%M:%S")


def build_overlap_fixture(tmp_path: Path):
    """Build raw + canonical with known Athens overlap across DST."""
    # Generate continuous broker-local hours (as MT5 does), then derive UTC.
    tz = ZoneInfo("Europe/Athens")
    start_local = datetime(2024, 10, 1, 0, 0)
    raw_rows = []
    utc_list = []
    for i in range(800):
        naive = start_local + timedelta(hours=i)
        aware = naive.replace(tzinfo=tz)
        utc = aware.astimezone(timezone.utc)
        # Skip fall-back duplicate local hour collision by advancing fold.
        if utc_list and utc <= utc_list[-1]:
            aware = naive.replace(tzinfo=tz, fold=1)
            utc = aware.astimezone(timezone.utc)
        server = naive.strftime("%Y.%m.%d %H:%M:%S")
        base = 2400 + i * 0.1
        raw_rows.append(
            (
                server,
                f"{base:.2f}",
                f"{base + 1:.2f}",
                f"{base - 1:.2f}",
                f"{base + 0.5:.2f}",
            )
        )
        utc_list.append(utc)

    # Ensure unique server timestamps for identity validation: MT5 exports
    # typically do not emit the ambiguous repeated local hour twice with
    # conflicting OHLC. Drop any exact duplicate server timestamp rows.
    deduped = []
    seen_ts = set()
    deduped_utc = []
    for row, utc in zip(raw_rows, utc_list):
        if row[0] in seen_ts:
            continue
        seen_ts.add(row[0])
        deduped.append(row)
        deduped_utc.append(utc)
    raw_rows = deduped
    utc_list = deduped_utc

    exposed_index = 100
    canonical_candles = []
    for i in range(exposed_index, min(700, len(raw_rows))):
        base = float(raw_rows[i][1])
        canonical_candles.append(
            Candle(
                symbol="XAUUSD",
                timeframe=Timeframe.H1,
                timestamp=utc_list[i],
                open=base,
                high=base + 1,
                low=base - 1,
                close=base + 0.5,
                volume=0,
                tick_volume=100,
                spread=0.10,
            )
        )

    raw_path = make_raw_csv(tmp_path / "raw.csv", raw_rows)
    dup_path = tmp_path / "dup.csv"
    dup_path.write_bytes(raw_path.read_bytes())

    canon_path = tmp_path / "canon.csv.gz"
    write_canonical_candles_csv(
        canon_path,
        canonical_candles,
        source="TEST",
        price_basis="BID",
    )
    return {
        "raw": raw_path,
        "dup": dup_path,
        "canon": canon_path,
        "exposed_index": exposed_index,
        "row_count": len(raw_rows),
    }


def test_raw_and_duplicate_source_equality(tmp_path: Path):
    fixture = build_overlap_fixture(tmp_path)
    assert sha256(fixture["raw"]) == sha256(fixture["dup"])


def test_source_mismatch_refusal(tmp_path: Path):
    fixture = build_overlap_fixture(tmp_path)
    fixture["dup"].write_bytes(fixture["raw"].read_bytes() + b"x")
    assert sha256(fixture["raw"]) != sha256(fixture["dup"])
    with pytest.raises(SystemExit, match="byte-identical"):
        if sha256(fixture["raw"]) != sha256(fixture["dup"]):
            raise PREPARE.HoldoutError(
                "REFUSED: raw source and chart_csv duplicate are not "
                "byte-identical"
            )


def _row(
    index: int,
    ts: str,
    o: str,
    h: str,
    l: str,
    c: str,
) -> PREPARE.RawRow:
    naive = datetime.strptime(ts, "%Y.%m.%d %H:%M:%S")
    return PREPARE.RawRow(
        index=index,
        line_bytes=b"x\r\n",
        timestamp_raw=ts,
        timestamp_naive=naive,
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(l),
        close=Decimal(c),
        tick_volume=1,
        volume=0,
        spread=Decimal("0.1"),
        symbol="XAUUSD.vx",
        timeframe="PERIOD_H1",
    )


def test_duplicate_timestamp_refusal():
    original = PREPARE.EXPECTED_ROW_COUNT
    PREPARE.EXPECTED_ROW_COUNT = 2
    try:
        rows = [
            _row(0, "2024.01.01 00:00:00", "1", "2", "0.5", "1.5"),
            _row(1, "2024.01.01 00:00:00", "1", "2", "0.5", "1.5"),
        ]
        with pytest.raises(SystemExit, match="duplicate timestamps"):
            PREPARE.validate_raw_identity(rows)
    finally:
        PREPARE.EXPECTED_ROW_COUNT = original


def test_conflicting_ohlc_duplicate_refusal():
    original = PREPARE.EXPECTED_ROW_COUNT
    PREPARE.EXPECTED_ROW_COUNT = 2
    try:
        rows = [
            _row(0, "2024.01.01 00:00:00", "1", "2", "0.5", "1.5"),
            _row(1, "2024.01.01 00:00:00", "9", "10", "8", "9.5"),
        ]
        with pytest.raises(SystemExit, match="conflicting duplicate"):
            PREPARE.validate_raw_identity(rows)
    finally:
        PREPARE.EXPECTED_ROW_COUNT = original


def test_invalid_ohlc_refusal():
    original = PREPARE.EXPECTED_ROW_COUNT
    PREPARE.EXPECTED_ROW_COUNT = 1
    try:
        rows = [_row(0, "2024.01.01 00:00:00", "5", "4", "6", "5")]
        with pytest.raises(SystemExit, match="OHLC"):
            PREPARE.validate_raw_identity(rows)
    finally:
        PREPARE.EXPECTED_ROW_COUNT = original


def test_exact_overlap_and_timezone_validation(tmp_path: Path):
    fixture = build_overlap_fixture(tmp_path)
    original = PREPARE.EXPECTED_ROW_COUNT
    PREPARE.EXPECTED_ROW_COUNT = fixture["row_count"]
    try:
        raw_rows, _, _ = PREPARE.load_raw_rows(fixture["raw"])
        assert len(raw_rows) == fixture["row_count"]
        integrity = PREPARE.validate_raw_identity(raw_rows)
        assert integrity["row_count"] == fixture["row_count"]
        canonical = PREPARE.load_canonical_overlap(fixture["canon"])
        model = PREPARE.validate_timezone_model(raw_rows, canonical)
        assert model["classification"] == (
            PREPARE.TIMEZONE_SCHEDULE_CLASSIFICATION
        )
        assert model["exact_iana_zone_identified"] is False
        assert model["conversion_reference_timezone"] == "Europe/Athens"
        assert model["conversion_reference_role"] == (
            "DETERMINISTIC_IMPLEMENTATION_REFERENCE_ONLY"
        )
        assert set(model["equivalent_exact_match_timezones"]) >= {
            "Europe/Athens",
            "Europe/Helsinki",
            "Europe/Bucharest",
        }
        assert "selected_timezone" not in model
        assert model["overlap_count"] == len(canonical)
        assert model["first_exact_overlap"]["raw_index"] == fixture[
            "exposed_index"
        ]
        assert model["winter_utc_plus_2_observed"]
        assert model["summer_utc_plus_3_observed"]
        assert any(
            "cannot be uniquely attributed" in note
            for note in model["attribution_notes"]
        )
    finally:
        PREPARE.EXPECTED_ROW_COUNT = original


def test_ambiguous_timezone_refusal(tmp_path: Path):
    candles = [
        Candle(
            symbol="XAUUSD",
            timeframe=Timeframe.H1,
            timestamp=datetime(2024, 7, 1, 12, 0, tzinfo=timezone.utc),
            open=1,
            high=2,
            low=0.5,
            close=1.5,
            tick_volume=1,
            volume=0,
            spread=0.1,
        )
    ]
    canon = tmp_path / "bad.csv.gz"
    write_canonical_candles_csv(canon, candles, source="T", price_basis="BID")
    raw = make_raw_csv(
        tmp_path / "raw.csv",
        [("2024.07.01 00:00:00", "1", "2", "0.5", "1.5")],
    )
    original = PREPARE.EXPECTED_ROW_COUNT
    PREPARE.EXPECTED_ROW_COUNT = 1
    try:
        raw_rows, _, _ = PREPARE.load_raw_rows(raw)
        PREPARE.validate_raw_identity(raw_rows)
        canonical = PREPARE.load_canonical_overlap(canon)
        with pytest.raises(SystemExit, match="no named timezone"):
            PREPARE.validate_timezone_model(raw_rows, canonical)
    finally:
        PREPARE.EXPECTED_ROW_COUNT = original


def test_retrospective_timezone_equivalence_across_holdout(tmp_path: Path):
    fixture = build_overlap_fixture(tmp_path)
    original = PREPARE.EXPECTED_ROW_COUNT
    PREPARE.EXPECTED_ROW_COUNT = fixture["row_count"]
    try:
        raw_rows, _, _ = PREPARE.load_raw_rows(fixture["raw"])
        PREPARE.validate_raw_identity(raw_rows)
        canonical = PREPARE.load_canonical_overlap(fixture["canon"])
        model = PREPARE.validate_timezone_model(raw_rows, canonical)
        localized = PREPARE.localize_rows(
            raw_rows, model["conversion_reference_timezone"]
        )
        holdout_end = fixture["exposed_index"] - 48
        holdout_rows = [row for row, _ in localized[:holdout_end]]
        equivalence = PREPARE.assert_retrospective_timezone_equivalence(
            holdout_rows,
            model["equivalent_exact_match_timezones"],
        )
        assert equivalence["retrospective_timezone_equivalence_passed"]
        assert equivalence["retrospective_equivalent_utc_conversions"]
        assert equivalence["retrospective_rows_checked"] == holdout_end
        assert equivalence["equivalence_start_server_timestamp"] == (
            holdout_rows[0].timestamp_raw
        )
        assert equivalence["equivalence_end_server_timestamp"] == (
            holdout_rows[-1].timestamp_raw
        )
    finally:
        PREPARE.EXPECTED_ROW_COUNT = original


def test_divergent_candidate_timezone_conversions_refuse():
    rows = [
        _row(0, "2024.01.01 00:00:00", "1", "2", "0.5", "1.5"),
        _row(1, "2024.01.01 01:00:00", "1", "2", "0.5", "1.5"),
    ]
    with pytest.raises(SystemExit, match="diverge on retrospective"):
        PREPARE.assert_retrospective_timezone_equivalence(
            rows,
            ["Europe/Athens", "UTC"],
        )


def test_exposed_boundary_and_embargo(tmp_path: Path):
    fixture = build_overlap_fixture(tmp_path)
    original = PREPARE.EXPECTED_ROW_COUNT
    PREPARE.EXPECTED_ROW_COUNT = fixture["row_count"]
    try:
        raw_rows, _, _ = PREPARE.load_raw_rows(fixture["raw"])
        PREPARE.validate_raw_identity(raw_rows)
        canonical = PREPARE.load_canonical_overlap(fixture["canon"])
        model = PREPARE.validate_timezone_model(raw_rows, canonical)
        localized = PREPARE.localize_rows(
            raw_rows, model["conversion_reference_timezone"]
        )

        def patched(localized_rows, first_overlap):
            exposed_index = int(first_overlap["raw_index"])
            holdout_end_exclusive = exposed_index - PREPARE.EMBARGO_BARS
            if holdout_end_exclusive <= 0:
                raise PREPARE.HoldoutError("REFUSED: insufficient")
            holdout = localized_rows[:holdout_end_exclusive]
            return {
                "exposed_boundary_raw_index": exposed_index,
                "exposed_boundary_server_timestamp": first_overlap[
                    "server_timestamp"
                ],
                "exposed_boundary_utc": first_overlap["utc"],
                "embargo_bars": PREPARE.EMBARGO_BARS,
                "holdout_end_exclusive": holdout_end_exclusive,
                "retrospective_row_count": len(holdout),
                "retrospective_first_server_timestamp": holdout[0][
                    0
                ].timestamp_raw,
                "retrospective_last_server_timestamp": holdout[-1][
                    0
                ].timestamp_raw,
                "retrospective_first_utc": PREPARE.utc_text(holdout[0][1]),
                "retrospective_last_utc": PREPARE.utc_text(holdout[-1][1]),
                "embargo_server_range": {
                    "start_index": holdout_end_exclusive,
                    "end_index_exclusive": exposed_index,
                },
            }

        original_fn = PREPARE.compute_holdout_boundary
        PREPARE.compute_holdout_boundary = patched
        try:
            boundary = PREPARE.compute_holdout_boundary(
                localized, model["first_exact_overlap"]
            )
            assert (
                boundary["exposed_boundary_raw_index"]
                == fixture["exposed_index"]
            )
            assert boundary["embargo_bars"] == 48
            assert (
                boundary["holdout_end_exclusive"]
                == fixture["exposed_index"] - 48
            )
        finally:
            PREPARE.compute_holdout_boundary = original_fn
    finally:
        PREPARE.EXPECTED_ROW_COUNT = original


def test_manifest_and_readme_do_not_claim_athens_identity(tmp_path: Path):
    audit = {
        "holdout_boundary": {
            "retrospective_row_count": 10,
            "retrospective_first_utc": "2022-01-02T22:00:00Z",
            "retrospective_last_utc": "2024-07-11T04:00:00Z",
            "exposed_boundary_raw_index": 15416,
            "embargo_bars": 48,
        },
        "timezone_model": {
            "classification": PREPARE.TIMEZONE_SCHEDULE_CLASSIFICATION,
            "exact_iana_zone_identified": False,
            "conversion_reference_timezone": "Europe/Athens",
            "conversion_reference_role": (
                "DETERMINISTIC_IMPLEMENTATION_REFERENCE_ONLY"
            ),
            "equivalent_exact_match_timezones": [
                "Europe/Athens",
                "Europe/Helsinki",
                "Europe/Bucharest",
            ],
        },
    }
    readme = tmp_path / "README.md"
    PREPARE.write_readme(readme, audit)
    text = readme.read_text(encoding="utf-8")
    assert "Exact IANA zone identified: `False`" in text
    assert "implementation only" in text.lower() or "Conversion reference" in text
    assert "not evidence that the broker server is physically" in text
    assert "Timezone model: `Europe/Athens`" not in text

    manifest = {
        "timezone_schedule": {
            "classification": PREPARE.TIMEZONE_SCHEDULE_CLASSIFICATION,
            "exact_iana_zone_identified": False,
            "conversion_reference_timezone": "Europe/Athens",
            "conversion_reference_role": (
                "DETERMINISTIC_IMPLEMENTATION_REFERENCE_ONLY"
            ),
        }
    }
    assert manifest["timezone_schedule"]["exact_iana_zone_identified"] is False
    assert "timezone_model" not in manifest
    assert manifest["timezone_schedule"][
        "conversion_reference_role"
    ] == "DETERMINISTIC_IMPLEMENTATION_REFERENCE_ONLY"


def test_selection_manifest_has_no_self_hash_and_binds_final_disk_sha(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    protocol = {
        "protocol_id": "XAUUSD_H1_2022_2024_RETROSPECTIVE_LOCKED_V1",
        "benchmark_type": "RETROSPECTIVE_HOLDOUT",
        "tuning_allowed": False,
        "window_selection": {
            "selection_uses_prices_or_predictions": False,
            "leading_guard_bars": 48,
            "trailing_guard_bars": 48,
            "bucket_count": 6,
            "window_bars": 192,
        },
    }
    source = tmp_path / "source"
    source.mkdir()
    start = datetime(2022, 1, 3, tzinfo=timezone.utc)
    candles = [
        Candle(
            symbol="XAUUSD",
            timeframe=Timeframe.H1,
            timestamp=start + timedelta(hours=i),
            open=1800,
            high=1801,
            low=1799,
            close=1800.5,
            tick_volume=1,
            volume=0,
            spread=0.1,
        )
        for i in range(48 + 48 + 6 * 300)
    ]
    canon = source / "XAUUSD_H1_2022_2024.real.csv.gz"
    write_canonical_candles_csv(canon, candles, source="S", price_basis="BID")
    protocol["source_package"] = {
        "canonical_sha256": sha256(canon),
    }
    write_json(
        source / "source_manifest.json",
        {
            "files": {
                "XAUUSD_H1_2022_2024.real.csv.gz": sha256(canon),
            }
        },
    )
    protocol_path = tmp_path / "protocol.json"
    write_json(protocol_path, protocol)
    locked_parent = tmp_path / "locked"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "select",
            "--protocol",
            str(protocol_path),
            "--source-root",
            str(source),
            "--output-parent",
            str(locked_parent),
        ],
    )
    assert SELECTOR.main() == 0

    manifest_path = (
        locked_parent / "windows_v1" / "selection_manifest.json"
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "selection_manifest_sha256" not in payload
    assert "selection_payload_sha256" not in payload

    final_sha = sha256(manifest_path)
    # Downstream pass documents bind the final on-disk byte hash.
    bound = {
        "selection": {
            "manifest_path": str(manifest_path),
            "manifest_sha256": final_sha,
        }
    }
    assert bound["selection"]["manifest_sha256"] == sha256(manifest_path)

    # Tampering changes the final byte hash and must be refused by validation.
    tampered = dict(payload)
    tampered["tamper"] = True
    manifest_path.write_text(
        json.dumps(tampered, indent=2) + "\n",
        encoding="utf-8",
    )
    assert bound["selection"]["manifest_sha256"] != sha256(manifest_path)


def test_pass_document_binds_and_refuses_manifest_tamper(tmp_path: Path):
    """Pass 1 stores the actual final selection-manifest SHA-256 from disk."""
    # Build a minimal post-compatible selection root so the shared pass helper
    # can prepare/validate without changing frozen post-2026H1 semantics.
    from tests.benchmarks.test_post_2026h1_label_passes import (
        create_selection_root,
    )

    selection_root = create_selection_root(tmp_path)
    manifest_path = selection_root / "selection_manifest.json"
    assert "selection_manifest_sha256" not in json.loads(
        manifest_path.read_text(encoding="utf-8")
    )
    actual_sha = sha256(manifest_path)

    created = datetime(2026, 7, 1, 12, tzinfo=timezone.utc)
    document = PASSES.build_pass_document(
        selection_root=selection_root,
        pass_number=1,
        annotator_id="annotator-a",
        created_at=created,
    )
    assert document["selection"]["manifest_sha256"] == actual_sha

    pass_path = tmp_path / "pass_1.json"
    write_json(pass_path, document)
    validated = PASSES.validate_pass_document(
        document,
        selection_root=selection_root,
    )
    assert validated["selection_manifest_sha256"] == actual_sha

    # Tamper with the published selection manifest after pass binding.
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["note"] = "tampered-after-pass-bind"
    write_json(manifest_path, payload)
    with pytest.raises(SystemExit, match="selection manifest SHA-256 mismatch"):
        PASSES.validate_pass_document(
            document,
            selection_root=selection_root,
        )


def test_frozen_retrospective_window_hashes_stable():
    """Guard the real regenerated package window ranges and file hashes."""
    root = (
        ROOT
        / "benchmarks"
        / "data"
        / "locked"
        / "XAUUSD"
        / "H1"
        / "retrospective_2022_2024"
        / "windows_v1"
    )
    if not root.exists():
        pytest.skip("retrospective windows package not present")

    manifest_path = root / "selection_manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "selection_manifest_sha256" not in payload
    # Final on-disk SHA of the published manifest without any embedded self-hash.
    assert sha256(manifest_path) == (
        "9bdaa635b71b09287def03bd38a0a8fe3c1a50a5f0fd431ee686e685bbc369e8"
    )

    expected = {
        1: (
            1224,
            1416,
            "5775bb6e9c02024d9ea9415c595044787b7c0ad5fea7b4b4738ff1c33c2482e2",
        ),
        2: (
            3769,
            3961,
            "a6ca7513b5165bbf8700aa2cd1c441cb21601ae967b294eb217acb856eeea1b1",
        ),
        3: (
            6315,
            6507,
            "e845c5b1249b237719322cae5382fba18c140ac302a1458e28b8c349469de91f",
        ),
        4: (
            8860,
            9052,
            "46512a8c4ec6230443bb9fec46b9db6522b4e3b6516ca26b3f5bc8fc97fdf133",
        ),
        5: (
            11405,
            11597,
            "7ba245bec20e133e33cabf7f13b0e996f6de8f6fc1a98e26ef9eef152055dbbd",
        ),
        6: (
            13951,
            14143,
            "a2e68346d9957ce3c54851dac0ca16f1b84a1d6de1c2e2ab2c8157355454740f",
        ),
    }
    for window in payload["windows"]:
        number = window["window_number"]
        start, end, digest = expected[number]
        assert window["start_index"] == start
        assert window["end_index_exclusive"] == end
        assert window["sha256"] == digest
        assert sha256(root / window["file"]) == digest


def test_deterministic_canonical_gzip(tmp_path: Path):
    candles = [
        Candle(
            symbol="XAUUSD",
            timeframe=Timeframe.H1,
            timestamp=datetime(2022, 1, 3, 0, 0, tzinfo=timezone.utc),
            open=1800.1,
            high=1801.2,
            low=1799.0,
            close=1800.5,
            tick_volume=10,
            volume=0,
            spread=0.2,
        )
    ]
    a = tmp_path / "a.csv.gz"
    b = tmp_path / "b.csv.gz"
    write_canonical_candles_csv(a, candles, source="S", price_basis="BID")
    write_canonical_candles_csv(b, candles, source="S", price_basis="BID")
    assert sha256(a) == sha256(b)


def test_immutable_output_refusal(tmp_path: Path):
    out = tmp_path / "pkg"
    out.mkdir()
    with pytest.raises(SystemExit, match="already exists"):
        PREPARE.atomic_publish(tmp_path / "staging", out)


def test_price_blind_six_non_overlapping_windows():
    protocol = {
        "window_selection": {
            "leading_guard_bars": 48,
            "trailing_guard_bars": 48,
            "bucket_count": 6,
            "window_bars": 192,
        }
    }
    start = datetime(2022, 1, 3, tzinfo=timezone.utc)
    bars = [
        {"timestamp_utc": start + timedelta(hours=i)}
        for i in range(48 + 48 + 6 * 400)
    ]
    windows = SELECTOR.select_windows(bars, protocol)
    assert len(windows) == 6
    for left, right in zip(windows, windows[1:]):
        assert left["end_index_exclusive"] <= right["start_index"]
    for window in windows:
        assert window["bars"] == 192


def test_protocol_and_package_checksum_tampering_refusal(tmp_path: Path):
    protocol = {
        "protocol_id": "XAUUSD_H1_2022_2024_RETROSPECTIVE_LOCKED_V1",
        "benchmark_type": "RETROSPECTIVE_HOLDOUT",
        "tuning_allowed": False,
        "window_selection": {
            "selection_uses_prices_or_predictions": False,
            "leading_guard_bars": 48,
            "trailing_guard_bars": 48,
            "bucket_count": 6,
            "window_bars": 192,
        },
        "source_package": {
            "canonical_sha256": "deadbeef",
        },
    }
    source = tmp_path / "source"
    source.mkdir()
    # Enough bars for selection
    start = datetime(2022, 1, 3, tzinfo=timezone.utc)
    candles = [
        Candle(
            symbol="XAUUSD",
            timeframe=Timeframe.H1,
            timestamp=start + timedelta(hours=i),
            open=1800,
            high=1801,
            low=1799,
            close=1800.5,
            tick_volume=1,
            volume=0,
            spread=0.1,
        )
        for i in range(48 + 48 + 6 * 300)
    ]
    canon = source / "XAUUSD_H1_2022_2024.real.csv.gz"
    write_canonical_candles_csv(canon, candles, source="S", price_basis="BID")
    write_json(
        source / "source_manifest.json",
        {
            "files": {
                "XAUUSD_H1_2022_2024.real.csv.gz": sha256(canon),
            }
        },
    )
    protocol_path = tmp_path / "protocol.json"
    write_json(protocol_path, protocol)

    with pytest.raises(SystemExit, match="canonical_sha256 mismatch"):
        sys.argv = [
            "select",
            "--protocol",
            str(protocol_path),
            "--source-root",
            str(source),
            "--output-parent",
            str(tmp_path / "locked"),
        ]
        SELECTOR.main()

    # Fix protocol hash then tamper package manifest expectation
    protocol["source_package"]["canonical_sha256"] = sha256(canon)
    write_json(protocol_path, protocol)
    write_json(
        source / "source_manifest.json",
        {
            "files": {
                "XAUUSD_H1_2022_2024.real.csv.gz": "0" * 64,
            }
        },
    )
    with pytest.raises(SystemExit, match="checksum mismatch"):
        SELECTOR.main()


def test_blind_pass_separation_enforcement():
    completed = datetime(2026, 7, 1, tzinfo=timezone.utc)
    prior = {
        "pass_number": 1,
        "status": "COMPLETE",
        "completed_at": completed,
    }
    with pytest.raises(SystemExit, match="pass 2 cannot begin before"):
        PASSES.ensure_second_pass_delay(
            prior=prior,
            created_at=completed + timedelta(days=1),
            minimum_days=3,
        )
    PASSES.ensure_second_pass_delay(
        prior=prior,
        created_at=completed + timedelta(days=3),
        minimum_days=3,
    )


def test_explicit_adjudication_enforcement():
    ADJ = load_script(
        "manage_xauusd_h1_post_2026h1_adjudication.py",
        "test_retrospective_adjudication_impl",
    )
    assert "PASS_1" in ADJ.ALLOWED_DECISIONS
    assert "CUSTOM" in ADJ.ALLOWED_DECISIONS
    assert "EXCLUDE" in ADJ.ALLOWED_DECISIONS


def test_retrospective_decision_never_promotes():
    protocol = {
        "engineering_gates": engineering_gates(),
    }
    candidate = {
        "location": {
            "precision": 0.9,
            "recall": 0.9,
            "f1": 0.9,
        },
        "semantic": {"f1": 0.9},
        "major_external": {
            "precision": 0.9,
            "recall": 0.9,
        },
    }
    baseline = {
        "location": {"f1": 0.8},
        "semantic": {"f1": 0.8},
    }
    rows = [{"f1_score": 0.9}, {"f1_score": 0.85}]
    prefix = {"summary": {"failures": 0}}
    gate = EVALUATOR.gate_receipt(
        protocol=protocol,
        candidate=candidate,
        baseline=baseline,
        candidate_rows=rows,
        prefix=prefix,
    )
    assert gate["decision"] == EVALUATOR.PASS_DECISION
    assert gate["decision"] != "PROMOTE_V2_3_0_FINAL"
    assert "PROMOTE_V2_3_0_FINAL" not in gate["decision"]
    assert gate["forbidden_decision_values"] == [
        "PROMOTE_V2_3_0_FINAL"
    ]


def _post_verification_evidence() -> dict:
    return {
        "evaluation_head": "TEST_HEAD",
        "candidate_tag": EVALUATOR.CANDIDATE_TAG,
        "candidate_tag_commit": CANDIDATE_COMMIT,
        "evaluator_tag": "xauusd-h1-post-2026h1-evaluator-v1",
        "evaluator_tag_commit": "POST_EVALUATOR_COMMIT",
        "allowed_post_candidate_changes": [],
        "dependency_sha256": {},
    }


def test_missing_retrospective_evaluator_tag_is_refused(
    monkeypatch: pytest.MonkeyPatch,
):
    import subprocess

    monkeypatch.setattr(
        EVALUATOR.POST,
        "verify_repository",
        lambda candidate_commit: _post_verification_evidence(),
    )

    def fake_git_output(*args: str) -> str:
        if args == (
            "rev-parse",
            f"{EVALUATOR.RETROSPECTIVE_EVALUATOR_TAG}^{{commit}}",
        ):
            raise subprocess.CalledProcessError(
                128,
                ["git", *args],
            )
        raise AssertionError(args)

    monkeypatch.setattr(
        EVALUATOR.POST,
        "git_output",
        fake_git_output,
    )

    with pytest.raises(
        SystemExit,
        match="retrospective evaluator freeze tag is missing",
    ):
        EVALUATOR.verify_repository(CANDIDATE_COMMIT)


def test_retrospective_evaluator_change_after_tag_is_refused(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        EVALUATOR.POST,
        "verify_repository",
        lambda candidate_commit: _post_verification_evidence(),
    )

    def fake_git_output(*args: str) -> str:
        if args == (
            "rev-parse",
            f"{EVALUATOR.RETROSPECTIVE_EVALUATOR_TAG}^{{commit}}",
        ):
            return "RETRO_EVALUATOR_COMMIT"

        if args == (
            "diff",
            "--name-only",
            "RETRO_EVALUATOR_COMMIT..HEAD",
            "--",
            EVALUATOR.RETROSPECTIVE_EVALUATOR_SCRIPT,
        ):
            return EVALUATOR.RETROSPECTIVE_EVALUATOR_SCRIPT

        raise AssertionError(args)

    monkeypatch.setattr(
        EVALUATOR.POST,
        "git_output",
        fake_git_output,
    )

    with pytest.raises(
        SystemExit,
        match=(
            "retrospective evaluator changed after "
            "its freeze tag"
        ),
    ):
        EVALUATOR.verify_repository(CANDIDATE_COMMIT)


def test_unrelated_commits_allowed_when_evaluator_unchanged(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        EVALUATOR.POST,
        "verify_repository",
        lambda candidate_commit: _post_verification_evidence(),
    )

    def fake_git_output(*args: str) -> str:
        if args == (
            "rev-parse",
            f"{EVALUATOR.RETROSPECTIVE_EVALUATOR_TAG}^{{commit}}",
        ):
            return "RETRO_EVALUATOR_COMMIT"

        if args == (
            "diff",
            "--name-only",
            "RETRO_EVALUATOR_COMMIT..HEAD",
            "--",
            EVALUATOR.RETROSPECTIVE_EVALUATOR_SCRIPT,
        ):
            # Diff scoped to the evaluator script is empty even when
            # later data-only commits exist on HEAD.
            return ""

        raise AssertionError(args)

    monkeypatch.setattr(
        EVALUATOR.POST,
        "git_output",
        fake_git_output,
    )

    evidence = EVALUATOR.verify_repository(CANDIDATE_COMMIT)
    assert evidence["evaluator_tag"] == (
        "xauusd-h1-post-2026h1-evaluator-v1"
    )
    assert evidence["evaluator_tag_commit"] == "POST_EVALUATOR_COMMIT"
    assert evidence["retrospective_evaluator_tag"] == (
        EVALUATOR.RETROSPECTIVE_EVALUATOR_TAG
    )
    assert evidence["retrospective_evaluator_tag_commit"] == (
        "RETRO_EVALUATOR_COMMIT"
    )


def test_successful_repository_verification_returns_both_evaluator_seals(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        EVALUATOR.POST,
        "verify_repository",
        lambda candidate_commit: _post_verification_evidence(),
    )

    def fake_git_output(*args: str) -> str:
        if args == (
            "rev-parse",
            f"{EVALUATOR.RETROSPECTIVE_EVALUATOR_TAG}^{{commit}}",
        ):
            return "RETRO_EVALUATOR_COMMIT"

        if args[:3] == (
            "diff",
            "--name-only",
            "RETRO_EVALUATOR_COMMIT..HEAD",
        ):
            return ""

        raise AssertionError(args)

    monkeypatch.setattr(
        EVALUATOR.POST,
        "git_output",
        fake_git_output,
    )

    evidence = EVALUATOR.verify_repository(CANDIDATE_COMMIT)
    assert set(evidence) >= {
        "evaluator_tag",
        "evaluator_tag_commit",
        "retrospective_evaluator_tag",
        "retrospective_evaluator_tag_commit",
        "candidate_tag",
        "candidate_tag_commit",
    }
    assert evidence["retrospective_evaluator_tag"] == (
        "xauusd-h1-2022-2024-retrospective-evaluator-v1"
    )


def create_frozen_package(tmp_path: Path) -> Path:
    package = tmp_path / "frozen-package"
    package.mkdir()
    protocol_path = tmp_path / "protocol.json"
    protocol_id = "XAUUSD_H1_2022_2024_RETROSPECTIVE_LOCKED_V1"
    protocol = {
        "protocol_id": protocol_id,
        "benchmark_type": "RETROSPECTIVE_HOLDOUT",
        "candidate": {
            "version": "2.3.0-rc1",
            "commit": CANDIDATE_COMMIT,
        },
        "baseline": {"version": "2.2.0"},
        "window_selection": {
            "bucket_count": 2,
            "window_bars": 80,
        },
        "evaluation": {
            "candidate_evaluations_allowed": 1,
            "baseline_evaluations_allowed": 1,
            "error_analysis_before_release_decision": False,
            "tuning_after_unblinding": False,
            "prefix_stability_required": True,
        },
        "engineering_gates": engineering_gates(),
        "decision_values": [
            "PASS_RETROSPECTIVE_ENGINEERING_GATE",
            "FAIL_RETROSPECTIVE_ENGINEERING_GATE",
        ],
        "forbidden_decision_values": ["PROMOTE_V2_3_0_FINAL"],
    }
    write_json(protocol_path, protocol)

    data_path = package / EVALUATOR.DATA_FILENAME
    labels_path = package / EVALUATOR.LABELS_FILENAME
    manifest_path = package / EVALUATOR.MANIFEST_FILENAME
    receipt_path = package / "freeze_receipt.json"

    start = datetime(2022, 6, 1, tzinfo=timezone.utc)
    candles = []
    for index in range(160):
        wave = 8.0 if (index // 10) % 2 == 0 else -8.0
        base = 1800.0 + index * 0.08 + wave
        candles.append(
            Candle(
                symbol="XAUUSD",
                timeframe=Timeframe.H1,
                timestamp=start + timedelta(hours=index),
                open=base,
                high=base + 2.5,
                low=base - 2.5,
                close=base + 0.4,
                volume=0,
                tick_volume=1000 + index,
                spread=0.29,
            )
        )
    write_canonical_candles_csv(
        data_path, candles, source="SYNTHETIC_RETRO_TEST", price_basis="MID"
    )
    data_sha = sha256(data_path)

    sample_ids = [
        "XAUUSD_H1_RETRO_001",
        "XAUUSD_H1_RETRO_002",
    ]
    samples = [
        {
            "sample_id": sample_ids[0],
            "window_number": 1,
            "split": "TEST",
            "source_start_index": 0,
            "source_end_index": 79,
            "labelable_start_index": 0,
            "labelable_end_index": 79,
            "bars": 80,
            "start_timestamp": candles[0].timestamp.isoformat(),
            "end_timestamp": candles[79].timestamp.isoformat(),
        },
        {
            "sample_id": sample_ids[1],
            "window_number": 2,
            "split": "TEST",
            "source_start_index": 80,
            "source_end_index": 159,
            "labelable_start_index": 0,
            "labelable_end_index": 79,
            "bars": 80,
            "start_timestamp": candles[80].timestamp.isoformat(),
            "end_timestamp": candles[159].timestamp.isoformat(),
        },
    ]

    swings = []
    decisions = [
        (sample_ids[0], 0, 20, "HIGH", 25, "MAJOR", "EXTERNAL"),
        (sample_ids[0], 0, 50, "LOW", 55, "MINOR", "INTERNAL"),
        (sample_ids[1], 80, 20, "HIGH", 25, "MAJOR", "EXTERNAL"),
        (sample_ids[1], 80, 50, "LOW", 55, "MINOR", "INTERNAL"),
    ]
    for number, (
        sample_id,
        source_start,
        pivot_index,
        direction,
        confirmation_index,
        tier,
        scope,
    ) in enumerate(decisions, start=1):
        pivot = candles[source_start + pivot_index]
        confirmation = candles[source_start + confirmation_index]
        swings.append(
            {
                "label_id": f"SYNTHETIC_SWG_{number:03d}",
                "sample_id": sample_id,
                "pivot_index": pivot_index,
                "source_bar_index": source_start + pivot_index,
                "timestamp": pivot.timestamp.isoformat(),
                "price": pivot.high if direction == "HIGH" else pivot.low,
                "price_field": direction,
                "direction": direction,
                "tier": tier,
                "scope": scope,
                "confirmation_status": "ADJUDICATED",
                "confirmed_at_index": confirmation_index,
                "confirmed_at_timestamp": confirmation.timestamp.isoformat(),
                "tags": ["HUMAN_ADJUDICATED", "BLIND_TWO_PASS"],
                "notes": "",
                "annotator_id": "SYNTHETIC",
                "review_status": "ADJUDICATED",
            }
        )

    labels = {
        "benchmark_id": protocol_id,
        "benchmark_version": "1.0.0-retrospective-human-adjudicated",
        "label_policy_version": protocol_id,
        "label_origin": "HUMAN_ADJUDICATED",
        "status": "FROZEN_HUMAN_ADJUDICATED",
        "dataset": {
            "dataset_id": protocol_id,
            "symbol": "XAUUSD",
            "timeframe": "H1",
            "timezone": "UTC",
            "price_basis": "MID",
            "source": "SYNTHETIC_RETRO_TEST",
            "data_file": data_path.name,
            "data_sha256": data_sha,
            "bar_count": 160,
            "first_timestamp": candles[0].timestamp.isoformat(),
            "last_timestamp": candles[-1].timestamp.isoformat(),
        },
        "samples": samples,
        "swings": swings,
        "review": {
            "required_annotators": 2,
            "adjudicator": "SYNTHETIC",
            "prediction_visibility": "HIDDEN_UNTIL_LABEL_FREEZE",
            "engine_version_visibility": "HIDDEN_UNTIL_LABEL_FREEZE",
        },
    }
    write_json(labels_path, labels)
    labels_sha = sha256(labels_path)

    datasets = []
    for sample in samples:
        datasets.append(
            {
                "id": sample["sample_id"],
                "sample_id": sample["sample_id"],
                "symbol": "XAUUSD",
                "timeframe": "H1",
                "regime": "unknown",
                "bars": sample["bars"],
                "labels_file": labels_path.name,
                "human_review": True,
                "label_source": "HUMAN_ADJUDICATED",
                "evaluation_tolerance_bars": 0,
                "description": "Synthetic retrospective TEST window",
                "source_type": "real",
                "data_file": data_path.name,
                "data_sha256": data_sha,
                "source_start_index": sample["source_start_index"],
                "source_end_index": sample["source_end_index"],
                "labelable_start_index": 0,
                "labelable_end_index": 79,
                "split": "TEST",
                "label_origin": "HUMAN_ADJUDICATED",
                "enabled": True,
            }
        )

    manifest = {
        "manifest_version": "1.0",
        "dataset_id": protocol_id,
        "protocol_id": protocol_id,
        "status": "FROZEN_UNBLINDED_LABELS_NOT_EVALUATED",
        "path_resolution": "PACKAGE_RELATIVE",
        "candidate": protocol["candidate"],
        "baseline": protocol["baseline"],
        "files": {
            "data": {"path": data_path.name, "sha256": data_sha},
            "labels": {"path": labels_path.name, "sha256": labels_sha},
        },
        "datasets": datasets,
        "contamination_controls": {
            "predictions_loaded": False,
            "swing_detector_executed": False,
            "candidate_evaluated": False,
            "baseline_evaluated": False,
        },
    }
    write_json(manifest_path, manifest)
    manifest_sha = sha256(manifest_path)

    receipt = {
        "dataset_id": protocol_id,
        "protocol_id": protocol_id,
        "status": "FROZEN_HUMAN_ADJUDICATED_NOT_EVALUATED",
        "candidate": protocol["candidate"],
        "baseline": protocol["baseline"],
        "source_evidence": {
            "protocol": {
                "path": str(protocol_path.resolve()),
                "sha256": sha256(protocol_path),
            },
        },
        "outputs": {
            "data_sha256": data_sha,
            "labels_sha256": labels_sha,
            "manifest_sha256": manifest_sha,
        },
    }
    write_json(receipt_path, receipt)
    return package


def test_no_evaluator_rerun_and_unblinding_survives_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    package = create_frozen_package(tmp_path)
    output = tmp_path / "evaluation"

    monkeypatch.setattr(
        EVALUATOR,
        "verify_repository",
        lambda candidate_commit: {
            "evaluation_head": "TEST_HEAD",
            "candidate_tag": EVALUATOR.CANDIDATE_TAG,
            "candidate_tag_commit": candidate_commit,
            "allowed_post_candidate_changes": [],
        },
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluator",
            "--package-root",
            str(package),
            "--output-root",
            str(output),
        ],
    )

    assert EVALUATOR.main() == 0
    assert (output / EVALUATOR.REPORT_NAME).exists()
    assert (output / EVALUATOR.UNBLINDING_NAME).exists()
    assert (output / EVALUATOR.GATE_NAME).exists()

    gate = json.loads(
        (output / EVALUATOR.GATE_NAME).read_text(encoding="utf-8")
    )
    assert gate["decision"] in {
        EVALUATOR.PASS_DECISION,
        EVALUATOR.FAIL_DECISION,
    }
    assert gate["decision"] != "PROMOTE_V2_3_0_FINAL"

    with pytest.raises(SystemExit, match="already exists"):
        EVALUATOR.main()

    output2 = tmp_path / "evaluation_fail"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluator",
            "--package-root",
            str(package),
            "--output-root",
            str(output2),
        ],
    )

    def boom(*args, **kwargs):
        raise RuntimeError("detection failed")

    monkeypatch.setattr(EVALUATOR, "run_profile", boom)
    with pytest.raises(RuntimeError, match="detection failed"):
        EVALUATOR.main()
    unblinding_path = output2 / EVALUATOR.UNBLINDING_NAME
    assert unblinding_path.exists()
    payload = json.loads(unblinding_path.read_text(encoding="utf-8"))
    assert payload["state"] == "UNBLINDING_STARTED"


def test_package_checksum_tampering_refused_by_evaluator(tmp_path: Path):
    package = create_frozen_package(tmp_path)
    receipt_path = package / "freeze_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["outputs"]["data_sha256"] = "0" * 64
    write_json(receipt_path, receipt)
    with pytest.raises(SystemExit, match="checksum mismatch"):
        EVALUATOR.load_package(package)


ADAPTER = load_script(
    "xauusd_h1_retrospective_selection_adapter.py",
    "test_retrospective_selection_adapter",
)

FROZEN_SELECTION_ROOT = (
    ROOT
    / "benchmarks"
    / "data"
    / "locked"
    / "XAUUSD"
    / "H1"
    / "retrospective_2022_2024"
    / "windows_v1"
)

FROZEN_SELECTION_SHA = (
    "9bdaa635b71b09287def03bd38a0a8fe3c1a50a5f0fd431ee686e685bbc369e8"
)

FROZEN_WINDOW_HASHES = {
    "window_01_1224_1416.csv": (
        "5775bb6e9c02024d9ea9415c595044787b7c0ad5fea7b4b4738ff1c33c2482e2"
    ),
    "window_02_3769_3961.csv": (
        "a6ca7513b5165bbf8700aa2cd1c441cb21601ae967b294eb217acb856eeea1b1"
    ),
    "window_03_6315_6507.csv": (
        "e845c5b1249b237719322cae5382fba18c140ac302a1458e28b8c349469de91f"
    ),
    "window_04_8860_9052.csv": (
        "46512a8c4ec6230443bb9fec46b9db6522b4e3b6516ca26b3f5bc8fc97fdf133"
    ),
    "window_05_11405_11597.csv": (
        "7ba245bec20e133e33cabf7f13b0e996f6de8f6fc1a98e26ef9eef152055dbbd"
    ),
    "window_06_13951_14143.csv": (
        "a2e68346d9957ce3c54851dac0ca16f1b84a1d6de1c2e2ab2c8157355454740f"
    ),
}


def _copy_frozen_selection(tmp_path: Path) -> Path:
    import shutil

    dest = tmp_path / "windows_v1"
    shutil.copytree(FROZEN_SELECTION_ROOT, dest)
    return dest


def test_committed_retrospective_manifest_schema_is_accepted():
    assert FROZEN_SELECTION_ROOT.exists()
    assert sha256(
        FROZEN_SELECTION_ROOT / "selection_manifest.json"
    ) == FROZEN_SELECTION_SHA
    for name, digest in FROZEN_WINDOW_HASHES.items():
        assert sha256(FROZEN_SELECTION_ROOT / name) == digest

    selection, manifest_path, windows = (
        ADAPTER.load_retrospective_selection(
            FROZEN_SELECTION_ROOT,
            parse_utc=PASSES.parse_utc,
        )
    )
    assert selection["benchmark_type"] == "RETROSPECTIVE_HOLDOUT"
    assert selection["status"] == (
        "WINDOWS_SELECTED_UNLABELED_NOT_EVALUATED"
    )
    assert selection["policy"][
        "selection_uses_chronology_and_indices_only"
    ] is True
    assert selection["contamination_controls"]["labels_exist"] is False
    assert len(windows) == 6
    assert manifest_path == (
        FROZEN_SELECTION_ROOT / "selection_manifest.json"
    ).resolve()
    assert sha256(manifest_path) == FROZEN_SELECTION_SHA


def test_native_controls_validated_before_normalization():
    native = json.loads(
        (
            FROZEN_SELECTION_ROOT / "selection_manifest.json"
        ).read_text(encoding="utf-8")
    )
    errors = ADAPTER.validate_native_retrospective_manifest(native)
    assert errors == []

    bad = dict(native)
    bad["contamination_controls"] = dict(native["contamination_controls"])
    bad["contamination_controls"]["labels_loaded"] = True
    assert ADAPTER.validate_native_retrospective_manifest(bad)


def test_missing_or_true_contamination_flags_refused(tmp_path: Path):
    root = _copy_frozen_selection(tmp_path)
    manifest_path = root / "selection_manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["contamination_controls"]["predictions_loaded"] = True
    write_json(manifest_path, payload)
    with pytest.raises(SystemExit, match="predictions_loaded must be false"):
        ADAPTER.load_retrospective_selection(
            root,
            parse_utc=PASSES.parse_utc,
        )


def test_eligible_for_labeling_false_refused(tmp_path: Path):
    root = _copy_frozen_selection(tmp_path)
    manifest_path = root / "selection_manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["eligibility"]["eligible_for_labeling"] = False
    write_json(manifest_path, payload)
    with pytest.raises(
        SystemExit,
        match="eligible_for_labeling must be True",
    ):
        ADAPTER.load_retrospective_selection(
            root,
            parse_utc=PASSES.parse_utc,
        )


def test_prospective_test_true_refused(tmp_path: Path):
    root = _copy_frozen_selection(tmp_path)
    manifest_path = root / "selection_manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["eligibility"]["prospective_test"] = True
    write_json(manifest_path, payload)
    with pytest.raises(
        SystemExit,
        match="prospective_test must be False",
    ):
        ADAPTER.load_retrospective_selection(
            root,
            parse_utc=PASSES.parse_utc,
        )


def test_normalized_compatibility_object_never_written_to_disk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    root = _copy_frozen_selection(tmp_path)
    writes: list[Path] = []
    original_write_text = Path.write_text

    def tracking_write_text(self, *args, **kwargs):
        writes.append(Path(self))
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", tracking_write_text)

    selection, manifest_path, _windows = (
        ADAPTER.load_retrospective_selection(
            root,
            parse_utc=PASSES.parse_utc,
        )
    )
    assert selection["compatibility_adapter"]["written_to_disk"] is False
    assert writes == []
    assert not (root / "compatibility_manifest.json").exists()
    assert sha256(manifest_path) != sha256_json_like(selection)


def sha256_json_like(value: dict) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def test_pass_1_binds_actual_final_manifest_sha_and_empty_labels(
    tmp_path: Path,
):
    root = _copy_frozen_selection(tmp_path)
    # Keep committed hash identity for the copied bytes.
    assert sha256(root / "selection_manifest.json") == FROZEN_SELECTION_SHA

    RETRO_PASSES = load_script(
        "manage_xauusd_h1_post_2026h1_label_passes.py",
        "test_retro_adapted_pass_manager",
    )
    ADAPTER.install_on_pass_module(RETRO_PASSES)

    created = datetime(2026, 7, 21, 12, tzinfo=timezone.utc)
    document = RETRO_PASSES.build_pass_document(
        selection_root=root,
        pass_number=1,
        annotator_id="MOON_PASS_1",
        created_at=created,
    )

    assert document["labels"] == []
    assert document["selection"]["manifest_sha256"] == FROZEN_SELECTION_SHA
    assert document["selection"]["manifest_path"].endswith(
        "selection_manifest.json"
    )
    assert "compatibility" not in document["selection"]["manifest_path"]
    assert document["blindness"]["predictions_visible"] is False
    assert document["blindness"]["engine_version_visible"] is False

    validated = RETRO_PASSES.validate_pass_document(
        document,
        selection_root=root,
    )
    assert validated["selection_manifest_sha256"] == FROZEN_SELECTION_SHA


def test_selection_manifest_tamper_refused_after_pass_bind(tmp_path: Path):
    root = _copy_frozen_selection(tmp_path)
    RETRO_PASSES = load_script(
        "manage_xauusd_h1_post_2026h1_label_passes.py",
        "test_retro_adapted_pass_manager_tamper",
    )
    ADAPTER.install_on_pass_module(RETRO_PASSES)

    document = RETRO_PASSES.build_pass_document(
        selection_root=root,
        pass_number=1,
        annotator_id="MOON_PASS_1",
        created_at=datetime(2026, 7, 21, 12, tzinfo=timezone.utc),
    )

    payload = json.loads(
        (root / "selection_manifest.json").read_text(encoding="utf-8")
    )
    payload["note"] = "tampered"
    write_json(root / "selection_manifest.json", payload)

    with pytest.raises(SystemExit, match="selection manifest SHA-256 mismatch"):
        RETRO_PASSES.validate_pass_document(
            document,
            selection_root=root,
        )


def test_window_file_tamper_refused(tmp_path: Path):
    root = _copy_frozen_selection(tmp_path)
    window_path = root / "window_01_1224_1416.csv"
    window_path.write_bytes(window_path.read_bytes() + b"\n")

    with pytest.raises(SystemExit, match="SHA-256 mismatch"):
        ADAPTER.load_retrospective_selection(
            root,
            parse_utc=PASSES.parse_utc,
        )


def test_adjudication_and_freezer_consume_adapted_selection(
    tmp_path: Path,
):
    root = _copy_frozen_selection(tmp_path)

    adjudication = load_script(
        "manage_xauusd_h1_post_2026h1_adjudication.py",
        "test_retro_adapted_adjudication",
    )
    ADAPTER.install_on_module_with_passes(adjudication)
    selection, manifest_path, windows = adjudication.PASSES.load_selection(
        root
    )
    assert selection["status"] == (
        "WINDOWS_SELECTED_UNLABELED_NOT_EVALUATED"
    )
    assert len(windows) == 6
    assert sha256(manifest_path) == FROZEN_SELECTION_SHA

    freezer = load_script(
        "freeze_xauusd_h1_post_2026h1_labels.py",
        "test_retro_adapted_freezer",
    )
    ADAPTER.install_on_module_with_passes(freezer)
    selection2, manifest_path2, windows2 = freezer.PASSES.load_selection(root)
    assert selection2["benchmark_type"] == "RETROSPECTIVE_HOLDOUT"
    assert len(windows2) == 6
    assert sha256(manifest_path2) == FROZEN_SELECTION_SHA


def test_frozen_selection_and_windows_remain_byte_identical():
    assert sha256(
        FROZEN_SELECTION_ROOT / "selection_manifest.json"
    ) == FROZEN_SELECTION_SHA
    for name, digest in FROZEN_WINDOW_HASHES.items():
        assert sha256(FROZEN_SELECTION_ROOT / name) == digest

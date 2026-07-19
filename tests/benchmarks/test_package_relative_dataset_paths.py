"""Tests for self-contained package-relative benchmark files."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from shared.types.models import Candle, Timeframe
from swing_engine.benchmark_data import (
    sha256_file,
    write_canonical_candles_csv,
)
from swing_engine.datasets import (
    DatasetSpec,
    _labels_path,
    load_real_bars,
    resolve_data_path,
)


def test_manifest_relative_data_and_labels_are_preferred(
    tmp_path: Path,
):
    package = tmp_path / "frozen-package"
    package.mkdir()

    manifest_path = package / "manifest.json"
    data_path = package / "candles.csv.gz"
    labels_path = package / "labels.json"

    start = datetime(
        2026,
        10,
        1,
        tzinfo=timezone.utc,
    )

    candles = [
        Candle(
            symbol="XAUUSD",
            timeframe=Timeframe.H1,
            timestamp=start + timedelta(hours=index),
            open=4000.0 + index,
            high=4002.0 + index,
            low=3998.0 + index,
            close=4001.0 + index,
            volume=0,
            tick_volume=1000 + index,
            spread=0.29,
        )
        for index in range(3)
    ]

    write_canonical_candles_csv(
        data_path,
        candles,
        source="TEST",
        price_basis="MID",
    )

    labels_path.write_text(
        json.dumps(
            {
                "label_origin": "HUMAN_ADJUDICATED",
                "swings": [],
            }
        ),
        encoding="utf-8",
    )

    manifest_path.write_text(
        json.dumps({"datasets": []}),
        encoding="utf-8",
    )

    spec = DatasetSpec(
        id="PACKAGE_TEST",
        symbol="XAUUSD",
        timeframe="H1",
        regime="unknown",
        bars=3,
        labels_file=labels_path.name,
        source_type="real",
        data_file=data_path.name,
        data_sha256=sha256_file(data_path),
        sample_id="PACKAGE_TEST",
        split="TEST",
        label_origin="HUMAN_ADJUDICATED",
    )

    assert resolve_data_path(
        spec,
        manifest_path=manifest_path,
    ) == data_path.resolve()

    assert _labels_path(
        spec,
        manifest_path=manifest_path,
    ) == labels_path.resolve()

    loaded = load_real_bars(
        spec,
        manifest_path=manifest_path,
    )

    assert len(loaded) == 3
    assert loaded[0].timestamp == start
    assert loaded[-1].close == 4003.0

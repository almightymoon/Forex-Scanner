from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from shared.types.models import Candle, Timeframe
from swing_engine.benchmark_data import (
    BenchmarkDataError,
    load_candles_csv,
    sha256_file,
    write_canonical_candles_csv,
)


def test_loads_mt5_style_csv_and_normalises_utc(tmp_path: Path):
    path = tmp_path / "mt5.csv"
    path.write_text(
        "<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>\n"
        "2025.01.02\t00:00:00\t2650.00\t2652.00\t2649.00\t2651.00\t100\t0\t0.20\n"
        "2025.01.02\t01:00:00\t2651.00\t2653.00\t2650.00\t2652.00\t120\t0\t0.22\n",
        encoding="utf-8",
    )
    bars = load_candles_csv(path, symbol="XAUUSD", timeframe="H1")
    assert len(bars) == 2
    assert bars[0].timestamp == datetime(2025, 1, 2, tzinfo=timezone.utc)
    assert bars[0].tick_volume == 100
    assert bars[0].spread == pytest.approx(0.20)


def test_canonical_round_trip_and_checksum(tmp_path: Path):
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    candles = [
        Candle(
            symbol="XAUUSD",
            timeframe=Timeframe.H1,
            timestamp=start + timedelta(hours=index),
            open=2600 + index,
            high=2601 + index,
            low=2599 + index,
            close=2600.5 + index,
            tick_volume=10 + index,
            spread=0.2,
        )
        for index in range(5)
    ]
    path = write_canonical_candles_csv(
        tmp_path / "bars.csv.gz", candles, source="TEST", price_basis="MID"
    )
    digest = sha256_file(path)
    loaded = load_candles_csv(
        path,
        symbol="XAUUSD",
        timeframe=Timeframe.H1,
        expected_sha256=digest,
    )
    assert [bar.close for bar in loaded] == [bar.close for bar in candles]
    with pytest.raises(BenchmarkDataError, match="Checksum mismatch"):
        load_candles_csv(
            path,
            symbol="XAUUSD",
            timeframe="H1",
            expected_sha256="0" * 64,
        )


def test_rejects_invalid_ohlc(tmp_path: Path):
    path = tmp_path / "bad.csv"
    path.write_text(
        "timestamp,open,high,low,close\n"
        "2025-01-01T00:00:00Z,10,9,8,10\n",
        encoding="utf-8",
    )
    with pytest.raises(BenchmarkDataError, match="inconsistent OHLC"):
        load_candles_csv(path, symbol="XAUUSD", timeframe="H1")


def test_converts_naive_broker_timezone_to_utc(tmp_path: Path):
    path = tmp_path / "broker.csv"
    path.write_text(
        "timestamp,open,high,low,close\n"
        "2025.01.02 02:00:00,2650,2652,2649,2651\n",
        encoding="utf-8",
    )
    bars = load_candles_csv(
        path,
        symbol="XAUUSD",
        timeframe="H1",
        naive_timezone="Europe/Helsinki",
    )
    assert bars[0].timestamp == datetime(2025, 1, 2, 0, 0, tzinfo=timezone.utc)

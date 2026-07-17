"""Canonical benchmark candle I/O and integrity checks.

The benchmark layer deliberately does not know about test fixtures.  A real
benchmark must be bound to one immutable candle file and verified by checksum
before labels or predictions are evaluated.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, TextIO
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from shared.types.models import Candle, Timeframe


class BenchmarkDataError(ValueError):
    """Raised when a benchmark candle file is missing, malformed, or changed."""


def sha256_file(path: Path) -> str:
    """Return the SHA-256 of the exact bytes stored on disk."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _open_text(path: Path, mode: str) -> TextIO:
    if "b" in mode:
        raise ValueError("benchmark CSV helpers operate in text mode")
    if path.suffix.lower() == ".gz":
        # mtime=0 keeps SHA-256 stable across rebuilds of the same CSV content.
        if "w" in mode:
            raw = gzip.GzipFile(filename="", mode="wb", fileobj=path.open("wb"), mtime=0)
            return io.TextIOWrapper(raw, encoding="utf-8", newline="")
        return gzip.open(path, mode, encoding="utf-8", newline="")
    return path.open(mode, encoding="utf-8", newline="")


def _normalise_header(value: str) -> str:
    return "".join(ch for ch in value.upper().strip().strip("<>") if ch.isalnum())


def _find_key(row: dict[str, str], *aliases: str) -> str | None:
    normalised = {_normalise_header(key): key for key in row}
    for alias in aliases:
        key = normalised.get(_normalise_header(alias))
        if key is not None:
            return key
    return None


def _parse_timestamp(row: dict[str, str], naive_timezone: str = "UTC") -> datetime:
    timestamp_key = _find_key(row, "timestamp", "timestamp_utc", "datetime", "date_time", "open_time_utc")
    if timestamp_key:
        raw = row[timestamp_key].strip()
    else:
        date_key = _find_key(row, "date")
        time_key = _find_key(row, "time")
        if not date_key or not time_key:
            raise BenchmarkDataError(
                "CSV needs TIMESTAMP/DATETIME or separate DATE and TIME columns"
            )
        raw = f"{row[date_key].strip()} {row[time_key].strip()}"

    raw = raw.replace("Z", "+00:00")
    candidates = (
        None,
        "%Y.%m.%d %H:%M:%S",
        "%Y.%m.%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
    )
    parsed: datetime | None = None
    for fmt in candidates:
        try:
            parsed = datetime.fromisoformat(raw) if fmt is None else datetime.strptime(raw, fmt)
            break
        except ValueError:
            continue
    if parsed is None:
        raise BenchmarkDataError(f"Unsupported timestamp format: {raw!r}")
    if parsed.tzinfo is None:
        try:
            parsed = parsed.replace(tzinfo=ZoneInfo(naive_timezone))
        except ZoneInfoNotFoundError as exc:
            raise BenchmarkDataError(f"Unknown source timezone: {naive_timezone}") from exc
    return parsed.astimezone(timezone.utc)


def _float_value(row: dict[str, str], name: str, *aliases: str) -> float:
    key = _find_key(row, name, *aliases)
    if key is None:
        raise BenchmarkDataError(f"CSV is missing required {name!r} column")
    raw = row[key].strip().replace(",", "")
    try:
        value = float(raw)
    except ValueError as exc:
        raise BenchmarkDataError(f"Invalid {name} value: {row[key]!r}") from exc
    if not math.isfinite(value):
        raise BenchmarkDataError(f"Non-finite {name} value: {value}")
    return value


def _int_value(row: dict[str, str], *aliases: str) -> int:
    key = _find_key(row, *aliases)
    if key is None or not row[key].strip():
        return 0
    try:
        return int(float(row[key].strip().replace(",", "")))
    except ValueError as exc:
        raise BenchmarkDataError(f"Invalid integer value: {row[key]!r}") from exc


def _reader(handle: TextIO) -> csv.DictReader:
    sample = handle.read(8192)
    handle.seek(0)
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(handle, dialect=dialect)
    if not reader.fieldnames:
        raise BenchmarkDataError("CSV has no header row")
    return reader


def load_candles_csv(
    path: Path,
    *,
    symbol: str,
    timeframe: Timeframe | str,
    expected_sha256: str | None = None,
    start_index: int | None = None,
    end_index: int | None = None,
    naive_timezone: str = "UTC",
) -> list[Candle]:
    """Load canonical or broker-exported OHLC into validated UTC candles.

    ``end_index`` is inclusive.  Index slicing happens after the complete file
    is validated so a bad row outside the selected sample cannot silently hide.
    """
    path = Path(path)
    if not path.exists():
        raise BenchmarkDataError(f"Benchmark data file does not exist: {path}")
    if expected_sha256:
        actual = sha256_file(path)
        if actual.lower() != expected_sha256.lower():
            raise BenchmarkDataError(
                f"Checksum mismatch for {path}: expected {expected_sha256}, got {actual}"
            )

    tf = timeframe if isinstance(timeframe, Timeframe) else Timeframe(timeframe)
    candles: list[Candle] = []
    previous_ts: datetime | None = None
    with _open_text(path, "rt") as handle:
        for row_number, row in enumerate(_reader(handle), start=2):
            if not row or not any(str(value or "").strip() for value in row.values()):
                continue
            try:
                ts = _parse_timestamp(row, naive_timezone=naive_timezone)
                open_ = _float_value(row, "open", "open_mid")
                high = _float_value(row, "high", "high_mid")
                low = _float_value(row, "low", "low_mid")
                close = _float_value(row, "close", "close_mid")
                tick_volume = _int_value(row, "tick_volume", "tickvol", "tickvolume", "ticks")
                volume = _int_value(row, "volume", "vol", "real_volume")
                spread_key = _find_key(row, "mean_spread", "spread")
                spread = float(row[spread_key]) if spread_key and row[spread_key].strip() else None
            except BenchmarkDataError as exc:
                raise BenchmarkDataError(f"{path}:{row_number}: {exc}") from exc

            if low > high:
                raise BenchmarkDataError(f"{path}:{row_number}: low is above high")
            if high < max(open_, close) or low > min(open_, close):
                raise BenchmarkDataError(f"{path}:{row_number}: inconsistent OHLC values")
            if previous_ts is not None and ts <= previous_ts:
                raise BenchmarkDataError(
                    f"{path}:{row_number}: timestamps are not strictly increasing ({ts.isoformat()})"
                )
            if spread is not None and (not math.isfinite(spread) or spread < 0):
                raise BenchmarkDataError(f"{path}:{row_number}: invalid spread {spread}")

            candles.append(
                Candle(
                    symbol=symbol.upper().replace("/", ""),
                    timeframe=tf,
                    timestamp=ts,
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume,
                    tick_volume=tick_volume,
                    spread=spread,
                )
            )
            previous_ts = ts

    if not candles:
        raise BenchmarkDataError(f"No candles were loaded from {path}")

    first = 0 if start_index is None else start_index
    last = len(candles) - 1 if end_index is None else end_index
    if first < 0 or last < first or last >= len(candles):
        raise BenchmarkDataError(
            f"Invalid candle slice [{first}, {last}] for file containing {len(candles)} bars"
        )
    return candles[first : last + 1]


def write_canonical_candles_csv(
    path: Path,
    candles: Iterable[Candle],
    *,
    source: str,
    price_basis: str = "MID",
) -> Path:
    """Write deterministic benchmark OHLC CSV (optionally gzip-compressed)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(candles)
    if not rows:
        raise BenchmarkDataError("Cannot write an empty benchmark candle file")

    with _open_text(path, "wt") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "bar_index",
                "timestamp_utc",
                "open",
                "high",
                "low",
                "close",
                "tick_volume",
                "volume",
                "mean_spread",
                "source",
                "price_basis",
            ]
        )
        for index, candle in enumerate(rows):
            ts = candle.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            else:
                ts = ts.astimezone(timezone.utc)
            writer.writerow(
                [
                    index,
                    ts.isoformat(),
                    f"{candle.open:.10f}",
                    f"{candle.high:.10f}",
                    f"{candle.low:.10f}",
                    f"{candle.close:.10f}",
                    candle.tick_volume,
                    candle.volume,
                    "" if candle.spread is None else f"{candle.spread:.10f}",
                    source,
                    price_basis,
                ]
            )
    return path


def canonicalise_csv(
    input_path: Path,
    output_path: Path,
    *,
    symbol: str,
    timeframe: Timeframe | str,
    source: str,
    price_basis: str = "MID",
    source_timezone: str = "UTC",
) -> tuple[Path, str, int]:
    """Validate a broker/vendor export and write the immutable canonical file."""
    candles = load_candles_csv(input_path, symbol=symbol, timeframe=timeframe, naive_timezone=source_timezone)
    write_canonical_candles_csv(output_path, candles, source=source, price_basis=price_basis)
    return output_path, sha256_file(output_path), len(candles)

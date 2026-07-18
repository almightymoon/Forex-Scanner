#!/usr/bin/env python3
"""Render blind XAUUSD H1 locked-test charts from raw candles only.

stdlib-only PNG renderer (no matplotlib / swing engine / label file).
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import struct
import zlib
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "benchmarks" / "datasets" / "XAUUSD_H1_2026H1.human.manifest.json"
OUTPUT = ROOT / "benchmarks" / "charts" / "XAUUSD" / "H1" / "locked_test_2026H1_blind"

# RGB
WHITE = (255, 255, 255)
BLACK = (30, 30, 30)
GRAY = (180, 180, 180)
GRID = (230, 230, 230)
GREEN = (24, 137, 119)
RED = (201, 75, 75)
GRAY_SHADE = (220, 220, 220)
DASH = (90, 90, 90)


def load_rows(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        # Support both raw export (`timestamp`) and canonical (`timestamp_utc`)
        rows = []
        for source_index, row in enumerate(reader):
            ts_raw = (row.get("timestamp_utc") or row.get("timestamp") or "").strip()
            rows.append(
                {
                    "source_index": source_index,
                    "timestamp": datetime.fromisoformat(ts_raw.replace("Z", "+00:00")),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                }
            )
    return rows


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def write_png(path: Path, width: int, height: int, pixels: bytearray) -> None:
    """Write RGB PNG. pixels length must be width*height*3."""
    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)  # filter none
        start = y * stride
        raw.extend(pixels[start : start + stride])
    compressed = zlib.compress(bytes(raw), 9)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", compressed)
        + _png_chunk(b"IEND", b"")
    )


class Canvas:
    def __init__(self, width: int, height: int, bg=WHITE):
        self.w = width
        self.h = height
        self.px = bytearray(width * height * 3)
        r, g, b = bg
        for i in range(0, len(self.px), 3):
            self.px[i] = r
            self.px[i + 1] = g
            self.px[i + 2] = b

    def _set(self, x: int, y: int, color) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.px[i], self.px[i + 1], self.px[i + 2] = color

    def fill_rect(self, x0: int, y0: int, x1: int, y1: int, color) -> None:
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        for y in range(max(0, y0), min(self.h, y1 + 1)):
            for x in range(max(0, x0), min(self.w, x1 + 1)):
                self._set(x, y, color)

    def vline(self, x: int, y0: int, y1: int, color, width: int = 1) -> None:
        for dx in range(-(width // 2), width // 2 + 1):
            for y in range(min(y0, y1), max(y0, y1) + 1):
                self._set(x + dx, y, color)

    def hline(self, y: int, x0: int, x1: int, color) -> None:
        for x in range(min(x0, x1), max(x0, x1) + 1):
            self._set(x, y, color)

    def dashed_vline(self, x: int, y0: int, y1: int, color) -> None:
        on = True
        for y in range(min(y0, y1), max(y0, y1) + 1):
            if on:
                self._set(x, y, color)
            if (y - y0) % 6 == 5:
                on = not on

    def save(self, path: Path) -> None:
        write_png(path, self.w, self.h, self.px)


def draw_sample(sample: dict, rows: list[dict]) -> Path:
    start = int(sample["source_start_index"])
    end = int(sample["source_end_index"])
    candles = rows[start : end + 1]

    expected = int(sample["bars"])
    if len(candles) != expected:
        raise ValueError(f"{sample['id']}: expected {expected} bars, found {len(candles)}")

    label_start = int(sample["labelable_start_index"])
    label_end = int(sample["labelable_end_index"])

    panels = [(0, 120), (90, 210), (180, len(candles))]
    panel_h = 420
    margin_top = 70
    margin_bottom = 30
    margin_x = 50
    width = 3200
    height = margin_top + panel_h * 3 + margin_bottom
    canvas = Canvas(width, height)

    # Title bar
    canvas.fill_rect(0, 0, width - 1, margin_top - 1, (245, 245, 245))

    plot_left = margin_x
    plot_right = width - margin_x
    plot_w = plot_right - plot_left

    for p_i, (panel_start, panel_end) in enumerate(panels):
        visible = candles[panel_start:panel_end]
        top = margin_top + p_i * panel_h
        bottom = top + panel_h - 40
        # panel background
        canvas.fill_rect(plot_left, top, plot_right, bottom, WHITE)

        # price scale
        highs = [c["high"] for c in visible]
        lows = [c["low"] for c in visible]
        p_max = max(highs)
        p_min = min(lows)
        pad = (p_max - p_min) * 0.05 or 1.0
        p_max += pad
        p_min -= pad

        def y_of(price: float) -> int:
            return int(bottom - (price - p_min) / (p_max - p_min) * (bottom - top))

        def x_of(sample_index: int) -> int:
            # map sample_index in [panel_start, panel_end) to plot x
            t = (sample_index - panel_start + 0.5) / max(panel_end - panel_start, 1)
            return int(plot_left + t * plot_w)

        # gray context regions
        if panel_start < label_start:
            x1 = x_of(min(label_start, panel_end) - 0.5) if min(label_start, panel_end) > panel_start else plot_left
            # approximate left shade
            shade_end_idx = min(label_start, panel_end)
            x_end = int(plot_left + (shade_end_idx - panel_start) / max(panel_end - panel_start, 1) * plot_w)
            canvas.fill_rect(plot_left, top, x_end, bottom, GRAY_SHADE)
        if panel_end - 1 > label_end:
            shade_start_idx = max(label_end + 1, panel_start)
            x_start = int(plot_left + (shade_start_idx - panel_start) / max(panel_end - panel_start, 1) * plot_w)
            canvas.fill_rect(x_start, top, plot_right, bottom, GRAY_SHADE)

        # grid
        for g in range(5):
            gy = top + int((bottom - top) * g / 4)
            canvas.hline(gy, plot_left, plot_right, GRID)

        # candles
        for local_offset, candle in enumerate(visible):
            sample_index = panel_start + local_offset
            x = x_of(sample_index)
            y_high = y_of(candle["high"])
            y_low = y_of(candle["low"])
            y_open = y_of(candle["open"])
            y_close = y_of(candle["close"])
            rising = candle["close"] >= candle["open"]
            color = GREEN if rising else RED
            canvas.vline(x, y_high, y_low, BLACK, width=1)
            body_top = min(y_open, y_close)
            body_bot = max(y_open, y_close)
            if body_bot - body_top < 2:
                body_bot = body_top + 2
            half = max(2, int(plot_w / max(panel_end - panel_start, 1) * 0.35))
            canvas.fill_rect(x - half, body_top, x + half, body_bot, color)

        # labelable dashed lines
        if panel_start <= label_start < panel_end:
            canvas.dashed_vline(x_of(label_start), top, bottom, DASH)
        if panel_start <= label_end < panel_end:
            canvas.dashed_vline(x_of(label_end), top, bottom, DASH)

        # border
        canvas.fill_rect(plot_left, top, plot_right, top, GRAY)
        canvas.fill_rect(plot_left, bottom, plot_right, bottom, GRAY)
        canvas.fill_rect(plot_left, top, plot_left, bottom, GRAY)
        canvas.fill_rect(plot_right, top, plot_right, bottom, GRAY)

    OUTPUT.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT / f"{sample['id']}.png"
    canvas.save(output_path)
    return output_path


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    if manifest["dataset_id"] != "XAUUSD_H1_2026H1_LOCKED_TEST_V1":
        raise ValueError("Unexpected dataset ID")

    samples = manifest["datasets"]
    if not samples or any(sample["split"] != "TEST" for sample in samples):
        raise ValueError("Every sample must be in the TEST split")

    relative_data_path = Path(samples[0]["data_file"])
    data_path = ROOT / "benchmarks" / relative_data_path

    actual_sha = hashlib.sha256(data_path.read_bytes()).hexdigest()
    expected_sha = manifest["data_sha256"]
    if actual_sha != expected_sha:
        raise ValueError(
            f"Data checksum mismatch: expected {expected_sha}, got {actual_sha}"
        )

    rows = load_rows(data_path)

    print(f"Dataset: {manifest['dataset_id']}")
    print(f"SHA-256: {actual_sha}")
    print(f"Source bars: {len(rows)}")

    for sample in samples:
        path = draw_sample(sample, rows)
        print(path)


if __name__ == "__main__":
    main()

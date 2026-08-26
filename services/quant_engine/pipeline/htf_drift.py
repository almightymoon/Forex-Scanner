"""Provider HTF vs Bar-Builder rollup comparison — observational only.

Does NOT alter MTF selection, scores, or signals. Enabled via
``HTF_DRIFT_TELEMETRY=true`` for staging logs.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Mapping

from shared.types.models import Candle, Timeframe

from services.quant_engine.pipeline.mtf_context import (
    DEFAULT_HTF_TARGETS,
    build_htf_bars_from_ltf,
    filter_completed_htf,
    htf_bar_available_at,
)

logger = logging.getLogger("fxnav.htf_drift")

# Relative OHLC tolerance for "structurally equivalent but numerically different"
_OHLC_REL_TOL = 1e-6
_OHLC_ABS_FLOOR = 1e-8


class HtfDriftKind(str, Enum):
    MATCH = "MATCH"
    EXPECTED_DIFFERENCE = "EXPECTED_DIFFERENCE"
    MISSING_PROVIDER_DATA = "MISSING_PROVIDER_DATA"
    MISSING_ROLLUP_DATA = "MISSING_ROLLUP_DATA"
    TIMESTAMP_MISMATCH = "TIMESTAMP_MISMATCH"
    OHLC_MISMATCH = "OHLC_MISMATCH"
    COMPLETION_MISMATCH = "COMPLETION_MISMATCH"
    STRUCTURAL_DIFFERENCE = "STRUCTURAL_DIFFERENCE"


@dataclass(frozen=True)
class HtfBarDiff:
    timeframe: str
    timestamp: str | None
    kind: HtfDriftKind
    detail: str
    provider_ohlc: tuple[float, float, float, float] | None = None
    rollup_ohlc: tuple[float, float, float, float] | None = None
    ohlc_delta: tuple[float, float, float, float] | None = None

    def to_dict(self) -> dict:
        return {
            "timeframe": self.timeframe,
            "timestamp": self.timestamp,
            "kind": self.kind.value,
            "detail": self.detail,
            "provider_ohlc": self.provider_ohlc,
            "rollup_ohlc": self.rollup_ohlc,
            "ohlc_delta": self.ohlc_delta,
        }


@dataclass(frozen=True)
class HtfDriftReport:
    symbol: str
    as_of: str
    provider_bar_counts: dict[str, int]
    rollup_bar_counts: dict[str, int]
    diffs: tuple[HtfBarDiff, ...]
    summary_kinds: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "as_of": self.as_of,
            "provider_bar_counts": dict(self.provider_bar_counts),
            "rollup_bar_counts": dict(self.rollup_bar_counts),
            "diffs": [d.to_dict() for d in self.diffs],
            "summary_kinds": list(self.summary_kinds),
        }

    @property
    def has_mismatch(self) -> bool:
        return any(d.kind is not HtfDriftKind.MATCH for d in self.diffs)


def htf_drift_telemetry_enabled() -> bool:
    return os.getenv("HTF_DRIFT_TELEMETRY", "").lower() in {"1", "true", "yes"}


def _ohlc(c: Candle) -> tuple[float, float, float, float]:
    return (c.open, c.high, c.low, c.close)


def _ohlc_close(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    for x, y in zip(a, b):
        scale = max(abs(x), abs(y), _OHLC_ABS_FLOOR)
        if abs(x - y) > max(_OHLC_ABS_FLOOR, _OHLC_REL_TOL * scale):
            return False
    return True


def _delta(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> tuple[float, float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2], a[3] - b[3])


def compare_htf_series(
    timeframe: str,
    provider: list[Candle],
    rollup: list[Candle],
    *,
    as_of: datetime,
) -> list[HtfBarDiff]:
    """Compare one TF series pair; classify each divergence."""
    diffs: list[HtfBarDiff] = []
    # Completion: bars present but not available as-of
    for c in provider:
        if not htf_bar_available_at(c, as_of):
            diffs.append(
                HtfBarDiff(
                    timeframe=timeframe,
                    timestamp=c.timestamp.isoformat(),
                    kind=HtfDriftKind.COMPLETION_MISMATCH,
                    detail="provider bar incomplete as-of",
                    provider_ohlc=_ohlc(c),
                )
            )
    for c in rollup:
        if not htf_bar_available_at(c, as_of):
            diffs.append(
                HtfBarDiff(
                    timeframe=timeframe,
                    timestamp=c.timestamp.isoformat(),
                    kind=HtfDriftKind.COMPLETION_MISMATCH,
                    detail="rollup bar incomplete as-of",
                    rollup_ohlc=_ohlc(c),
                )
            )

    p_done = {c.timestamp: c for c in filter_completed_htf(provider, as_of)}
    r_done = {c.timestamp: c for c in filter_completed_htf(rollup, as_of)}

    if not p_done and r_done:
        diffs.append(
            HtfBarDiff(
                timeframe=timeframe,
                timestamp=None,
                kind=HtfDriftKind.MISSING_PROVIDER_DATA,
                detail=f"provider empty; rollup has {len(r_done)} completed bars",
            )
        )
        return diffs
    if p_done and not r_done:
        diffs.append(
            HtfBarDiff(
                timeframe=timeframe,
                timestamp=None,
                kind=HtfDriftKind.MISSING_ROLLUP_DATA,
                detail=f"rollup empty; provider has {len(p_done)} completed bars",
            )
        )
        return diffs

    only_p = set(p_done) - set(r_done)
    only_r = set(r_done) - set(p_done)
    for ts in sorted(only_p):
        c = p_done[ts]
        diffs.append(
            HtfBarDiff(
                timeframe=timeframe,
                timestamp=ts.isoformat(),
                kind=HtfDriftKind.MISSING_ROLLUP_DATA,
                detail="timestamp present in provider only",
                provider_ohlc=_ohlc(c),
            )
        )
    for ts in sorted(only_r):
        c = r_done[ts]
        diffs.append(
            HtfBarDiff(
                timeframe=timeframe,
                timestamp=ts.isoformat(),
                kind=HtfDriftKind.MISSING_PROVIDER_DATA,
                detail="timestamp present in rollup only",
                rollup_ohlc=_ohlc(c),
            )
        )

    # Align by index when timestamps differ but counts match → TIMESTAMP_MISMATCH
    if only_p or only_r:
        if len(p_done) == len(r_done) and len(p_done) > 0:
            diffs.append(
                HtfBarDiff(
                    timeframe=timeframe,
                    timestamp=None,
                    kind=HtfDriftKind.TIMESTAMP_MISMATCH,
                    detail="same completed count but differing timestamps",
                )
            )
        elif abs(len(p_done) - len(r_done)) > 0 and (only_p or only_r):
            # Already emitted missing_*; if shapes diverge heavily mark structural
            if abs(len(p_done) - len(r_done)) >= max(3, len(p_done) // 2):
                diffs.append(
                    HtfBarDiff(
                        timeframe=timeframe,
                        timestamp=None,
                        kind=HtfDriftKind.STRUCTURAL_DIFFERENCE,
                        detail=(
                            f"completed counts diverge provider={len(p_done)} "
                            f"rollup={len(r_done)}"
                        ),
                    )
                )

    for ts in sorted(set(p_done) & set(r_done)):
        pc, rc = p_done[ts], r_done[ts]
        po, ro = _ohlc(pc), _ohlc(rc)
        if _ohlc_close(po, ro):
            diffs.append(
                HtfBarDiff(
                    timeframe=timeframe,
                    timestamp=ts.isoformat(),
                    kind=HtfDriftKind.MATCH,
                    detail="ohlc match",
                    provider_ohlc=po,
                    rollup_ohlc=ro,
                    ohlc_delta=(0.0, 0.0, 0.0, 0.0),
                )
            )
        else:
            # Small relative drift → EXPECTED_DIFFERENCE; large → OHLC_MISMATCH
            max_rel = 0.0
            for x, y in zip(po, ro):
                scale = max(abs(x), abs(y), _OHLC_ABS_FLOOR)
                max_rel = max(max_rel, abs(x - y) / scale)
            kind = (
                HtfDriftKind.EXPECTED_DIFFERENCE
                if max_rel < 0.001
                else HtfDriftKind.OHLC_MISMATCH
            )
            diffs.append(
                HtfBarDiff(
                    timeframe=timeframe,
                    timestamp=ts.isoformat(),
                    kind=kind,
                    detail=f"ohlc relative delta max={max_rel:.6g}",
                    provider_ohlc=po,
                    rollup_ohlc=ro,
                    ohlc_delta=_delta(po, ro),
                )
            )

    if not diffs and not p_done and not r_done:
        diffs.append(
            HtfBarDiff(
                timeframe=timeframe,
                timestamp=None,
                kind=HtfDriftKind.MATCH,
                detail="both empty",
            )
        )
    return diffs


def compare_htf_context(
    *,
    symbol: str,
    ltf_candles: list[Candle],
    provider_htf: Mapping[str, list[Candle]] | None,
    as_of: datetime | None = None,
    targets: tuple[Timeframe, ...] | None = None,
) -> HtfDriftReport:
    """Compare provider HTF maps against Bar Builder rollup from LTF prefix."""
    if not ltf_candles:
        raise ValueError("ltf_candles required")
    as_of_ts = as_of or ltf_candles[-1].timestamp
    targets = targets or DEFAULT_HTF_TARGETS
    rollup = build_htf_bars_from_ltf(ltf_candles, targets=targets, as_of=as_of_ts)
    provider = {
        k: filter_completed_htf(list(v), as_of_ts)
        for k, v in (provider_htf or {}).items()
    }

    all_diffs: list[HtfBarDiff] = []
    p_counts: dict[str, int] = {}
    r_counts: dict[str, int] = {}
    keys = sorted(set(provider) | set(rollup) | {t.value for t in targets})
    for key in keys:
        # Skip TFs we cannot roll from this LTF (e.g. M15 from H1)
        p_series = provider.get(key, [])
        r_series = rollup.get(key, [])
        p_counts[key] = len(p_series)
        r_counts[key] = len(r_series)
        if not p_series and not r_series:
            continue
        all_diffs.extend(
            compare_htf_series(key, p_series, r_series, as_of=as_of_ts)
        )

    kinds = tuple(sorted({d.kind.value for d in all_diffs}))
    return HtfDriftReport(
        symbol=symbol,
        as_of=as_of_ts.isoformat(),
        provider_bar_counts=p_counts,
        rollup_bar_counts=r_counts,
        diffs=tuple(all_diffs),
        summary_kinds=kinds,
    )


def maybe_log_htf_drift(
    *,
    symbol: str,
    ltf_candles: list[Candle],
    provider_htf: Mapping[str, list[Candle]] | None,
    as_of: datetime | None = None,
) -> HtfDriftReport | None:
    """If telemetry enabled, compare and log compact drift summary. Never mutates inputs."""
    if not htf_drift_telemetry_enabled():
        return None
    report = compare_htf_context(
        symbol=symbol,
        ltf_candles=ltf_candles,
        provider_htf=provider_htf,
        as_of=as_of,
    )
    # Compact: one log line per non-MATCH diff (cap 20)
    logged = 0
    for diff in report.diffs:
        if diff.kind is HtfDriftKind.MATCH:
            continue
        logger.info(
            "htf_drift symbol=%s tf=%s as_of=%s kind=%s ts=%s detail=%s delta=%s",
            report.symbol,
            diff.timeframe,
            report.as_of,
            diff.kind.value,
            diff.timestamp,
            diff.detail,
            diff.ohlc_delta,
        )
        logged += 1
        if logged >= 20:
            break
    if logged == 0:
        logger.debug(
            "htf_drift symbol=%s as_of=%s status=clean counts_p=%s counts_r=%s",
            report.symbol,
            report.as_of,
            report.provider_bar_counts,
            report.rollup_bar_counts,
        )
    return report

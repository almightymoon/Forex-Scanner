"""Higher-timeframe context for MTF — causal availability contract.

Contract
--------
* HTF bars are represented as ``list[Candle]`` with ``candle.timeframe`` set.
* Construction: prefer provider/collector series; otherwise
  ``rollup_bars`` from Bar Builder (no second aggregation algorithm).
* Availability: an HTF bar that opens at ``timestamp`` with duration ``D``
  seconds is **available** only when ``as_of >= timestamp + D``.
  Incomplete / forming HTF bars must not affect earlier LTF decisions.
* ``resolve_mtf_trends`` maps available HTF series → ``TrendDirection`` via
  Market Structure external bias (EMA fallback when structure is ranging).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Mapping

from shared.types.models import Candle, Timeframe, TrendDirection

from services.bar_builder.constants import TF_SECONDS
from services.bar_builder.rollup import rollup_bars
from services.indicator_service.indicators import compute_all
from services.quant_engine.market_structure.mtf_bias import structure_bias_for_candles

# Default HTF set relative to an H1 primary scan (matches live DataLoader).
DEFAULT_HTF_TARGETS: tuple[Timeframe, ...] = (
    Timeframe.M15,
    Timeframe.H4,
    Timeframe.D1,
)


def _aware(ts: datetime) -> datetime:
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)


def htf_bar_available_at(candle: Candle, as_of: datetime) -> bool:
    """True when the HTF bar is fully closed relative to ``as_of``."""
    seconds = TF_SECONDS.get(candle.timeframe)
    if seconds is None:
        return _aware(candle.timestamp) <= _aware(as_of)
    close_at = _aware(candle.timestamp) + timedelta(seconds=seconds)
    return close_at <= _aware(as_of)


def filter_completed_htf(
    candles: list[Candle],
    as_of: datetime,
) -> list[Candle]:
    """Drop forming / future HTF bars not closed by ``as_of``."""
    return [c for c in candles if htf_bar_available_at(c, as_of)]


def build_htf_bars_from_ltf(
    ltf_candles: list[Candle],
    targets: tuple[Timeframe, ...] | None = None,
    *,
    as_of: datetime | None = None,
) -> dict[str, list[Candle]]:
    """Roll LTF prefix into HTF via Bar Builder ``rollup_bars``, then causal-filter."""
    if not ltf_candles:
        return {}
    as_of_ts = as_of or ltf_candles[-1].timestamp
    source_tf = ltf_candles[0].timeframe
    source_sec = TF_SECONDS.get(source_tf, 0)
    out: dict[str, list[Candle]] = {}
    for tf in targets or DEFAULT_HTF_TARGETS:
        target_sec = TF_SECONDS.get(tf, 0)
        if target_sec <= source_sec and tf is not source_tf:
            # Only roll *up*. Lower TFs need a real series.
            continue
        if tf is source_tf:
            series = list(ltf_candles)
        else:
            series = rollup_bars(ltf_candles, tf)
        out[tf.value] = filter_completed_htf(series, as_of_ts)
    return out


def merge_htf_bars(
    primary: list[Candle],
    provided: Mapping[str, list[Candle]] | None,
    *,
    targets: tuple[Timeframe, ...] | None = None,
    as_of: datetime | None = None,
) -> dict[str, list[Candle]]:
    """Prefer provided HTF series; fill gaps by rolling the primary LTF prefix."""
    as_of_ts = as_of or (primary[-1].timestamp if primary else datetime.now(timezone.utc))
    provided = provided or {}
    merged: dict[str, list[Candle]] = {}
    for key, series in provided.items():
        if series:
            merged[key] = filter_completed_htf(list(series), as_of_ts)

    rolled = build_htf_bars_from_ltf(primary, targets=targets, as_of=as_of_ts)
    for key, series in rolled.items():
        if key not in merged or len(merged[key]) < 50:
            # Use rollup when provider series missing or too short for structure.
            if key not in merged or not merged[key]:
                merged[key] = series
            elif len(merged[key]) < 50 and len(series) >= len(merged[key]):
                merged[key] = series
    return merged


def resolve_mtf_trends(
    primary_candles: list[Candle],
    bars_by_timeframe: Mapping[str, list[Candle]] | None = None,
    *,
    as_of: datetime | None = None,
    min_bars: int = 50,
    include_primary: bool = False,
) -> dict[str, TrendDirection]:
    """Build causal MTF trend map from available HTF bars.

    Structure external bias wins when committed; else EMA20/50 on that TF.
    """
    if not primary_candles:
        return {}
    as_of_ts = as_of or primary_candles[-1].timestamp
    bars = merge_htf_bars(
        primary_candles,
        bars_by_timeframe,
        as_of=as_of_ts,
    )
    if include_primary:
        key = primary_candles[0].timeframe.value
        bars.setdefault(key, filter_completed_htf(list(primary_candles), as_of_ts))

    trends: dict[str, TrendDirection] = {}
    for tf_key in sorted(bars.keys()):
        series = bars[tf_key]
        if len(series) < min_bars:
            continue
        bias, _ = structure_bias_for_candles(series, min_bars=min_bars)
        if bias.source == "structure" and bias.bias is not TrendDirection.RANGING:
            trends[tf_key] = bias.bias
            continue
        ind = compute_all(series, series[0].symbol, series[0].timeframe)
        if ind.ema_20 and ind.ema_50:
            if ind.ema_20 > ind.ema_50:
                trends[tf_key] = TrendDirection.BULLISH
            elif ind.ema_20 < ind.ema_50:
                trends[tf_key] = TrendDirection.BEARISH
            else:
                trends[tf_key] = TrendDirection.RANGING
    return trends


def select_ranking_htf_trend(
    mtf_trends: Mapping[str, TrendDirection] | None,
    primary: Timeframe | str,
) -> tuple[TrendDirection | None, str | None]:
    """Select the canonical HTF trend used by zone ranking.

    Picks the **nearest higher** timeframe present in the already-resolved
    ``mtf_trends`` map (from :func:`resolve_mtf_trends`). Does not recompute
    trend. Returns ``(None, None)`` when no higher-TF trend is available —
    callers may fall back to LTF structure bias for ``trend_alignment``.
    """
    if not mtf_trends:
        return None, None
    if isinstance(primary, Timeframe):
        primary_tf = primary
    else:
        try:
            primary_tf = Timeframe(str(primary))
        except ValueError:
            return None, None
    primary_sec = TF_SECONDS.get(primary_tf, 0)
    candidates: list[tuple[int, str, TrendDirection]] = []
    for key, trend in mtf_trends.items():
        try:
            tf = Timeframe(str(key))
        except ValueError:
            continue
        sec = TF_SECONDS.get(tf, 0)
        if sec > primary_sec:
            candidates.append((sec, tf.value, trend))
    if not candidates:
        return None, None
    candidates.sort(key=lambda item: (item[0], item[1]))
    _sec, tf_key, trend = candidates[0]
    return trend, tf_key

"""Structured explainability payload for the transparency dashboard."""

from shared.config.scanner import ScoringConfig, get_scanner_config
from shared.types.models import NewsContext, SMCPattern, SignalDirection

from .models import MomentumAnalysis, SRAnalysis, TrendAnalysis, VolumeAnalysis


def build_detected_patterns(smc_reasons: list[str], smc_patterns: list[SMCPattern]) -> list[dict]:
    """Human-readable SMC checklist for the UI."""
    patterns: list[dict] = []
    seen: set[str] = set()

    for p in smc_patterns:
        key = p.pattern_type
        if key in seen:
            continue
        seen.add(key)
        label = _pattern_label(p.pattern_type, p.direction)
        patterns.append({"id": key, "label": label, "direction": p.direction.value})

    for reason in smc_reasons:
        label = reason.split(" detected")[0] if " detected" in reason else reason
        key = label.lower().replace(" ", "_")
        if key not in seen:
            patterns.append({"id": key, "label": label, "direction": "neutral"})

    return patterns


def build_score_deltas(
    trend: TrendAnalysis,
    momentum: MomentumAnalysis,
    smc_reasons: list[str],
    sr: SRAnalysis,
    volume: VolumeAnalysis,
    mtf_score: int,
    mtf_aligned: bool,
    news: NewsContext,
    smc_patterns: list[SMCPattern],
    config: ScoringConfig | None = None,
) -> list[dict]:
    """Point-by-point ledger: why the score moved up or down."""
    cfg = config or get_scanner_config().scoring
    deltas: list[dict] = []

    def add(text: str, delta: int) -> None:
        if delta == 0:
            return
        deltas.append({
            "text": text,
            "delta": delta,
            "sign": "+" if delta > 0 else "−",
        })

    tr = cfg.trend.rules
    if trend.ema_aligned:
        add("EMA stack aligned with trend", tr["ema_alignment"].points)
    if trend.adx_strong:
        add("ADX confirms trend strength", tr["adx_strong"].points)
    if trend.higher_highs:
        add("Higher highs in structure", tr["higher_highs"].points)
    if trend.higher_lows:
        add("Higher lows in structure", tr["higher_lows"].points)
    if trend.price_above_vwap:
        add("Price above VWAP", tr["price_above_vwap"].points)

    mo = cfg.momentum.rules
    if momentum.macd_bullish:
        add("MACD histogram aligned", mo["macd_histogram"].points)
    if momentum.rsi_in_zone:
        add("RSI in trend zone", mo["rsi_in_zone"].points)
    if momentum.atr_rising:
        add("ATR volatility expansion", mo["atr_expansion"].points)

    smc_rules = cfg.smc.rules
    seen_smc: set[str] = set()
    for p in smc_patterns:
        if p.pattern_type in seen_smc:
            continue
        seen_smc.add(p.pattern_type)
        rule = smc_rules.get(p.pattern_type)
        pts = rule.points if rule else 2
        label = _pattern_label(p.pattern_type, p.direction)
        add(f"{label} detected", pts)

    sr_rules = cfg.risk_sr.rules
    if sr.near_support:
        add("Price near support", sr_rules["near_support"].points)
    if sr.near_resistance:
        add("Price near resistance", sr_rules["near_resistance"].points)
    if sr.fib_confluence:
        add("Fibonacci confluence", sr_rules["fib_confluence"].points)
    if sr.pivot_confirmed:
        add("Pivot level confirmed", sr_rules["pivot_confirmed"].points)

    vol_rules = cfg.risk_volume.rules
    if volume.volume_above_avg:
        add("Volume above average", vol_rules["volume_above_avg"].points)
    if volume.atr_expanding:
        add("ATR expansion on candle", vol_rules["atr_expanding"].points)
    if volume.breakout_strength:
        add("Strong breakout candle", vol_rules["breakout_strength"].points)
    if not volume.spread_normal:
        add("Elevated spread", vol_rules["spread_penalty"].points)

    if mtf_aligned:
        add("Multi-timeframe alignment", cfg.mtf.rules["full_alignment"].points)
    elif mtf_score < cfg.mtf.rules["partial_default"].points:
        add("Timeframes not fully aligned", mtf_score - cfg.mtf.rules["partial_default"].points)

    if news.has_high_impact_soon:
        if news.minutes_until_event and news.minutes_until_event <= 30:
            add("High-impact news imminent", cfg.news.rules["high_impact_imminent"].points - cfg.news.rules["clear"].points)
        else:
            add("High-impact news approaching", cfg.news.rules["high_impact_soon"].points - cfg.news.rules["clear"].points)

    return deltas


def build_evidence_checklist(
    outputs: list[dict],
    smc_patterns: list[SMCPattern],
    news: NewsContext,
    session: str,
    historical: dict | None = None,
) -> list[dict]:
    """Structured evidence items for the transparency dashboard."""
    items: list[dict] = []
    pattern_types = {p.pattern_type for p in smc_patterns}

    def add(label: str, passed: bool, category: str = "technical") -> None:
        items.append({"label": label, "passed": passed, "category": category})

    add("BOS detected", "bos" in pattern_types)
    add("CHoCH detected", "choch" in pattern_types)
    add("Fresh Order Block", "order_block" in pattern_types)
    add("Liquidity Sweep", "liquidity_sweep" in pattern_types)
    add("Fair Value Gap", "fvg" in pattern_types)
    add(f"{session.replace('_', ' ').title()} Session", session not in ("off_hours",))
    add("No High Impact News", not news.has_high_impact_soon, "risk")

    ms = next((o for o in outputs if o.get("name") == "Market Structure"), None)
    if ms and ms.get("metadata", {}).get("best_quality", 0) >= 70:
        add(f"Strong BOS quality ({ms['metadata']['best_quality']}/100)", True)

    if historical and historical.get("sample_size", 0) >= 10:
        wr = historical.get("win_rate", 0)
        add(f"Historical win rate {wr}% ({historical['sample_size']} setups)", wr >= 50, "historical")

    return items


def build_explainability_summary(
    score: int,
    confidence: float,
    decision_factors: list[dict],
    detected_patterns: list[dict],
    score_deltas: list[dict],
    session: str,
    evidence: list[dict] | None = None,
    historical: dict | None = None,
) -> dict:
    if decision_factors and decision_factors[0].get("name"):
        categories = [
            {"label": f["name"], "score": f["score"], "max_score": f["max_score"]}
            for f in decision_factors
        ]
    else:
        categories = _ui_categories(decision_factors)

    return {
        "score": score,
        "confidence": confidence,
        "confidence_pct": round(confidence * 100),
        "session": session,
        "categories": categories,
        "detected_patterns": detected_patterns,
        "score_deltas": score_deltas,
        "evidence": evidence or [],
        "historical": historical,
    }


def _ui_categories(factors: list[dict]) -> list[dict]:
    """Merge MTF into market structure for the retail explainability view."""
    by_cat = {f["category"]: f for f in factors}
    trend = by_cat.get("trend", {})
    momentum = by_cat.get("momentum", {})
    smc = by_cat.get("smc", {})
    mtf = by_cat.get("mtf", {})
    risk = by_cat.get("risk", {})
    news = by_cat.get("news", {})

    ms_score = smc.get("score", 0) + mtf.get("score", 0)
    ms_max = 30

    return [
        {"label": "Trend", "score": trend.get("score", 0), "max_score": trend.get("max_score", 20)},
        {"label": "Momentum", "score": momentum.get("score", 0), "max_score": momentum.get("max_score", 15)},
        {"label": "Market Structure", "score": min(ms_score, ms_max), "max_score": ms_max},
        {"label": "Risk", "score": risk.get("score", 0), "max_score": min(risk.get("max_score", 20), 15)},
        {"label": "News", "score": news.get("score", 0), "max_score": news.get("max_score", 10)},
    ]


def _pattern_label(pattern_type: str, direction: SignalDirection) -> str:
    name = pattern_type.replace("_", " ").title()
    if pattern_type == "bos":
        name = "BOS"
    if pattern_type == "fvg":
        name = "Fair Value Gap Filled"
    prefix = "Bullish" if direction == SignalDirection.BUY else "Bearish" if direction == SignalDirection.SELL else ""
    if prefix and prefix.lower() not in name.lower():
        return f"{prefix} {name}"
    return name

"""Trading session detection and session-based score weighting."""

from datetime import datetime, timezone

from shared.config.scanner import ScoringConfig, get_scanner_config


def current_session(now: datetime | None = None) -> str:
    hour = (now or datetime.now(timezone.utc)).hour
    if 13 <= hour < 16:
        return "london_ny_overlap"
    if 8 <= hour < 16:
        return "london"
    if 13 <= hour < 21:
        return "new_york"
    if 0 <= hour < 8:
        return "asia"
    return "off_hours"


def session_weight(session: str | None = None, config: ScoringConfig | None = None) -> float:
    cfg = config or get_scanner_config().scoring
    session = session or current_session()
    return cfg.session_weights.get(session, 1.0)

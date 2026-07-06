"""Trading session detection and session-based score weighting."""

from datetime import datetime, timezone


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


def session_weight(session: str | None = None, weights: dict[str, float] | None = None) -> float:
    from shared.config.scoring_loader import get_v2_scoring_config
    cfg_weights = weights or get_v2_scoring_config().session_weights
    session = session or current_session()
    return cfg_weights.get(session, 1.0)

"""Startup banner — makes provider and simulation mode impossible to miss."""

import logging
import os

from shared.config.market import get_market_config, is_simulated_mode

logger = logging.getLogger("fxnav.startup")

_PROVIDER_LABELS = {
    "twelvedata": "Twelve Data",
    "polygon": "Polygon",
    "simulated": "Simulated (development only)",
}


def print_startup_banner(resolved_provider: str | None = None) -> None:
    cfg = get_market_config()
    provider_key = resolved_provider or cfg.provider.default
    label = _PROVIDER_LABELS.get(provider_key, provider_key.title())
    simulated = is_simulated_mode()
    fallback = cfg.provider.fallback_enabled

    has_twelve = bool(os.getenv("TWELVE_DATA_API_KEY", ""))
    has_polygon = bool(os.getenv("POLYGON_API_KEY", ""))

    lines = [
        "",
        "=" * 52,
    ]
    if simulated:
        lines.append("⚠  RUNNING IN SIMULATION MODE")
        lines.append(f"   Provider: {label}")
    else:
        lines.append(f"✔  Active provider: {label}")
        lines.append("✔  Simulation: DISABLED")
        lines.append(
            f"{'✔' if has_twelve else '✗'}  Twelve Data: {'configured' if has_twelve else 'missing key'}"
        )
        lines.append(
            f"{'✔' if has_polygon else '✗'}  Polygon: {'configured' if has_polygon else 'missing key'}"
        )
        lines.append(f"{'✔' if not fallback else '⚠'}  Failover: {'DISABLED' if not fallback else 'ENABLED'}")
    lines.append("=" * 52)
    lines.append("")

    for line in lines:
        logger.warning(line) if simulated else logger.info(line)

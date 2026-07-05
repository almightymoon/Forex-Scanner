"""Startup banner — makes provider and simulation mode impossible to miss."""

import logging

from shared.config.market import get_market_config, is_simulated_mode

logger = logging.getLogger("fxnav.startup")

_PROVIDER_LABELS = {
    "twelvedata": "Twelve Data",
    "polygon": "Polygon",
    "oanda": "OANDA",
    "mt5": "MetaTrader 5",
    "frankfurter": "Frankfurter (live rates only)",
    "simulated": "Simulated",
}


def print_startup_banner(resolved_provider: str | None = None) -> None:
    cfg = get_market_config()
    provider_key = resolved_provider or cfg.provider.default
    label = _PROVIDER_LABELS.get(provider_key, provider_key.title())
    simulated = is_simulated_mode()
    fallback = cfg.provider.allow_fallback

    lines = [
        "",
        "=" * 52,
    ]
    if simulated:
        lines.append("⚠  RUNNING IN SIMULATION MODE")
        lines.append(f"   Provider: {label}")
    else:
        lines.append(f"✔  Provider: {label}")
        lines.append("✔  Simulation: DISABLED")
        lines.append(f"{'✔' if not fallback else '⚠'}  Fallback: {'DISABLED' if not fallback else 'ENABLED'}")
    lines.append("=" * 52)
    lines.append("")

    for line in lines:
        logger.warning(line) if simulated else logger.info(line)

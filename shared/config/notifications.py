"""Notification / alert configuration."""

from dataclasses import dataclass
from functools import lru_cache
import os


@dataclass(frozen=True)
class NotificationsConfig:
    telegram_bot_token: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    min_alert_score: int = 80
    default_delivery: tuple[str, ...] = ("push",)
    alert_cooldown_seconds: int = 300


@lru_cache
def get_notifications_config() -> NotificationsConfig:
    return NotificationsConfig(
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        smtp_host=os.getenv("SMTP_HOST", ""),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        min_alert_score=int(os.getenv("MIN_ALERT_SCORE", "80")),
    )

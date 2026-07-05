"""Shared configuration."""

import os
from functools import lru_cache


class Settings:
  DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://fxnav:fxnav_dev@localhost:5432/fxnavigators",
  )
  REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
  JWT_SECRET: str = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
  JWT_ALGORITHM: str = "HS256"
  JWT_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

  # Scanner defaults
  MIN_ALERT_SCORE: int = 80
  SCAN_INTERVAL_SECONDS: int = 60
  DEFAULT_TIMEFRAMES: list[str] = ["M15", "H1", "H4"]

  # Market data
  OANDA_API_KEY: str = os.getenv("OANDA_API_KEY", "")
  OANDA_ACCOUNT_ID: str = os.getenv("OANDA_ACCOUNT_ID", "")
  TWELVE_DATA_API_KEY: str = os.getenv("TWELVE_DATA_API_KEY", "")
  POLYGON_API_KEY: str = os.getenv("POLYGON_API_KEY", "")
  MARKET_DATA_PROVIDER: str = os.getenv("MARKET_DATA_PROVIDER", "frankfurter")

  # AI
  OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

  # Notifications
  TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
  SMTP_HOST: str = os.getenv("SMTP_HOST", "")
  SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))

  # Billing
  STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
  STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
  STRIPE_PRICE_PRO: str = os.getenv("STRIPE_PRICE_PRO", "")
  STRIPE_PRICE_ELITE: str = os.getenv("STRIPE_PRICE_ELITE", "")


@lru_cache
def get_settings() -> Settings:
  return Settings()

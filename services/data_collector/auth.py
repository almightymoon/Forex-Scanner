"""API key authentication for internal /market endpoints."""

import os

from fastapi import Header, HTTPException, status


def verify_market_api_key(
    x_market_api_key: str | None = Header(None, alias="X-Market-Api-Key"),
) -> None:
    """
    Protect /market/* routes with MARKET_API_KEY.

    When MARKET_API_KEY is unset, endpoints remain open (local development only).
    """
    expected = os.getenv("MARKET_API_KEY", "")
    if not expected:
        return
    if not x_market_api_key or x_market_api_key != expected:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Invalid or missing X-Market-Api-Key header",
        )

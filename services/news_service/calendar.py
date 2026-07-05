"""Economic calendar and news impact service."""

import json
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Optional

from shared.types.models import NewsContext, NewsImpact


class NewsService:
    """
    Fetches economic calendar events and evaluates news risk per currency.
    Uses free ForexFactory JSON mirror when available; falls back to curated events.
    """

    def __init__(self):
        self._cache: list[dict] = []
        self._cache_time: Optional[datetime] = None

    async def get_events(self, days: int = 7) -> list[dict]:
        if self._cache_time and (datetime.now(timezone.utc) - self._cache_time).seconds < 3600:
            return self._cache

        events = self._fetch_ff_calendar() or self._default_events()
        self._cache = events
        self._cache_time = datetime.now(timezone.utc)
        return events

    def _fetch_ff_calendar(self) -> Optional[list[dict]]:
        """Try fetching from a public economic calendar JSON feed."""
        try:
            url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
            req = urllib.request.Request(url, headers={"User-Agent": "FXNavigators/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = json.loads(resp.read())

            events = []
            for item in raw:
                impact_map = {"High": "high", "Medium": "medium", "Low": "low"}
                impact = impact_map.get(item.get("impact", ""), "low")
                if impact == "low":
                    continue
                events.append({
                    "currency": item.get("country", "USD")[:3].upper(),
                    "title": item.get("title", "Economic Event"),
                    "impact": impact,
                    "forecast": item.get("forecast"),
                    "previous": item.get("previous"),
                    "actual": item.get("actual"),
                    "event_time": item.get("date", datetime.now(timezone.utc).isoformat()),
                })
            return events if events else None
        except Exception:
            return None

    def _default_events(self) -> list[dict]:
        now = datetime.now(timezone.utc)
        return [
            {
                "currency": "USD",
                "title": "Non-Farm Payrolls",
                "impact": "high",
                "forecast": "180K",
                "previous": "175K",
                "event_time": (now + timedelta(days=3)).isoformat(),
            },
            {
                "currency": "EUR",
                "title": "ECB Interest Rate Decision",
                "impact": "high",
                "forecast": "4.25%",
                "previous": "4.50%",
                "event_time": (now + timedelta(days=2)).isoformat(),
            },
            {
                "currency": "GBP",
                "title": "GDP Growth Rate QoQ",
                "impact": "medium",
                "forecast": "0.2%",
                "previous": "0.1%",
                "event_time": (now + timedelta(hours=8)).isoformat(),
            },
            {
                "currency": "USD",
                "title": "CPI m/m",
                "impact": "high",
                "forecast": "0.3%",
                "previous": "0.4%",
                "event_time": (now + timedelta(days=5)).isoformat(),
            },
        ]

    def evaluate_news_risk(self, symbol: str, events: list[dict]) -> NewsContext:
        """Score news risk for a currency pair based on upcoming events."""
        base = symbol[:3]
        quote = symbol[3:6] if len(symbol) >= 6 else ""
        currencies = {base, quote}
        now = datetime.now(timezone.utc)

        worst_impact = NewsImpact.LOW
        nearest_minutes: Optional[int] = None
        nearest_title: Optional[str] = None

        for event in events:
            if event.get("currency") not in currencies:
                continue
            try:
                event_time = datetime.fromisoformat(
                    event["event_time"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                continue

            delta = (event_time - now).total_seconds() / 60
            if delta < 0 or delta > 240:
                continue

            impact = NewsImpact(event.get("impact", "low"))
            if impact == NewsImpact.HIGH and (nearest_minutes is None or delta < nearest_minutes):
                nearest_minutes = int(delta)
                nearest_title = event["title"]
                worst_impact = NewsImpact.HIGH
            elif impact == NewsImpact.MEDIUM and worst_impact != NewsImpact.HIGH:
                worst_impact = NewsImpact.MEDIUM

        has_high = worst_impact == NewsImpact.HIGH and nearest_minutes is not None
        score = 10
        if has_high and nearest_minutes <= 30:
            score = 0
        elif has_high and nearest_minutes <= 120:
            score = 3
        elif worst_impact == NewsImpact.MEDIUM:
            score = 5

        return NewsContext(
            has_high_impact_soon=has_high,
            minutes_until_event=nearest_minutes,
            event_title=nearest_title,
            impact=worst_impact,
            score=score,
        )

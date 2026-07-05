"""AI-powered trade explanations with template fallback."""

import json
import urllib.request
from typing import Optional

from shared.configs.settings import get_settings
from shared.types.models import ScannerSignal

settings = get_settings()


class AIExplainer:
    """Generates human-readable explanations. Uses OpenAI when configured."""

    def __init__(self):
        self._api_key = settings.OPENAI_API_KEY

    async def explain(self, signal: ScannerSignal) -> str:
        if self._api_key:
            try:
                return await self._openai_explain(signal)
            except Exception:
                pass
        return self._enhanced_template(signal)

    async def _openai_explain(self, signal: ScannerSignal) -> str:
        import asyncio

        prompt = self._build_prompt(signal)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._call_openai, prompt)

    def _call_openai(self, prompt: str) -> str:
        payload = json.dumps({
            "model": "gpt-4o-mini",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a professional forex analyst for FX Navigators. "
                        "Explain trade setups clearly and honestly. Never guarantee profits. "
                        "Keep responses under 150 words. Be specific about technical factors."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 250,
            "temperature": 0.4,
        }).encode()

        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"].strip()

    def _build_prompt(self, signal: ScannerSignal) -> str:
        bd = signal.score_breakdown
        label = "Gold (XAU/USD)" if signal.symbol == "XAUUSD" else signal.symbol
        return f"""Analyze this forex scanner setup:

Pair: {label}
Direction: {signal.direction.value.upper()}
Score: {signal.score}/100 ({signal.rating.value})
Trend: {signal.trend.value}
Risk: {signal.risk_level.value}
Timeframe: {signal.timeframe.value}

Score breakdown:
- Trend: {bd.trend}/20
- SMC: {bd.smc}/25
- Momentum: {bd.momentum}/15
- S/R: {bd.support_resistance}/10
- Volume: {bd.volume_volatility}/10
- MTF: {bd.mtf_alignment}/10
- News: {bd.news_risk}/10

Technical: {', '.join(signal.technical_reasons[:4])}
SMC: {', '.join(signal.smc_reasons[:4])}
Entry: {signal.entry_zone_low}–{signal.entry_zone_high}
SL: {signal.stop_loss} | TP1: {signal.take_profit_1} | R:R {signal.risk_reward}

Write a clear, professional explanation a trader can act on."""

    def _enhanced_template(self, signal: ScannerSignal) -> str:
        label = "Gold (XAU/USD)" if signal.symbol == "XAUUSD" else signal.symbol
        parts = [
            f"{label} — {signal.direction.value.upper()} — {signal.score}/100 ({signal.rating.value})",
            "",
        ]

        if signal.symbol == "XAUUSD":
            parts.append("Gold is trading against the US Dollar. Safe-haven flows and USD strength are key drivers.")

        bd = signal.score_breakdown
        if bd.trend >= 15:
            parts.append(f"Strong {signal.trend.value} trend confirmed across moving averages.")
        elif bd.trend >= 8:
            parts.append(f"Moderate {signal.trend.value} trend detected.")

        if bd.smc >= 18:
            parts.append("Institutional SMC patterns align — smart money footprint is clear.")
        elif bd.smc >= 10:
            parts.append("Some SMC patterns detected supporting the directional bias.")

        if bd.momentum >= 10:
            parts.append("Momentum indicators confirm the move has strength behind it.")

        if bd.mtf_alignment >= 8:
            parts.append("Multiple timeframes agree on direction — higher probability setup.")
        elif bd.mtf_alignment < 5:
            parts.append("Caution: timeframes are not fully aligned.")

        if bd.news_risk <= 3:
            parts.append("High-impact news nearby — consider waiting or reducing size.")
        else:
            parts.append("No major news events threatening this setup in the near term.")

        if signal.risk_reward and signal.risk_reward >= 1.5:
            parts.append(f"Risk/reward of {signal.risk_reward}:1 offers favorable asymmetry.")

        parts.append(f"\nConfidence: {signal.score}/100 | Risk level: {signal.risk_level.value}")
        return "\n".join(parts)

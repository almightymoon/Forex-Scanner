"""Notification delivery — Telegram, Discord, console."""

import json
import urllib.request
from typing import Optional

from shared.configs.settings import get_settings
from shared.types.models import ScannerSignal

settings = get_settings()


class NotificationService:
    def __init__(self):
        self._log: list[dict] = []

    async def notify_signal(
        self,
        signal: ScannerSignal,
        methods: Optional[list[str]] = None,
        chat_id: Optional[str] = None,
        webhook_url: Optional[str] = None,
    ) -> list[str]:
        methods = methods or ["console"]
        sent = []
        title = f"{signal.symbol} {signal.direction.value.upper()} — {signal.score}/100"
        body = signal.ai_explanation or f"{signal.rating.value} setup on {signal.timeframe.value}"

        for method in methods:
            try:
                if method == "telegram":
                    if await self._send_telegram(title, body, chat_id):
                        sent.append("telegram")
                elif method == "discord":
                    if await self._send_discord(title, body, webhook_url):
                        sent.append("discord")
                elif method == "console":
                    print(f"[ALERT] {title}\n{body}")
                    sent.append("console")
            except Exception as e:
                print(f"[NOTIFY ERROR] {method}: {e}")

        self._log.append({"title": title, "methods": sent, "symbol": signal.symbol})
        return sent

    async def _send_telegram(self, title: str, body: str, chat_id: Optional[str]) -> bool:
        token = settings.TELEGRAM_BOT_TOKEN
        cid = chat_id or ""
        if not token or not cid:
            print(f"[TELEGRAM] (no credentials) {title}")
            return False

        text = f"*{title}*\n\n{body}"
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({"chat_id": cid, "text": text, "parse_mode": "Markdown"}).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200

    async def _send_discord(self, title: str, body: str, webhook_url: Optional[str]) -> bool:
        url = webhook_url or ""
        if not url:
            print(f"[DISCORD] (no webhook) {title}")
            return False

        payload = json.dumps({
            "embeds": [{
                "title": title,
                "description": body[:2000],
                "color": 3447003,
            }]
        }).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status in (200, 204)

    def get_log(self) -> list[dict]:
        return self._log

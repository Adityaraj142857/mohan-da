"""Free Telegram Bot API notifier (SPEC section 12) via plain httpx — no SDK."""

from __future__ import annotations

import logging

import httpx

from shopbot.notify.console import ConsoleNotifier

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str, fallback: ConsoleNotifier | None = None):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.fallback = fallback or ConsoleNotifier()

    def notify_owner(self, event_type: str, payload: dict) -> None:
        self.fallback.notify_owner(event_type, payload)
        if not self.bot_token or not self.chat_id:
            return
        text = f"🔔 {event_type}\n" + "\n".join(f"{k}: {v}" for k, v in payload.items())
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        try:
            httpx.post(url, json={"chat_id": self.chat_id, "text": text}, timeout=5.0)
        except httpx.HTTPError:
            logger.exception("telegram notify failed")

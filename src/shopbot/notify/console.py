"""Free default notifier: log + an in-memory feed the admin dashboard reads."""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger("shopbot.owner")


@dataclass
class OwnerAlert:
    ts: datetime
    event_type: str
    payload: dict


class ConsoleNotifier:
    def __init__(self, maxlen: int = 200):
        self.feed: deque[OwnerAlert] = deque(maxlen=maxlen)

    def notify_owner(self, event_type: str, payload: dict) -> None:
        alert = OwnerAlert(ts=datetime.now(timezone.utc), event_type=event_type, payload=payload)
        self.feed.appendleft(alert)
        logger.info("owner alert: %s %s", event_type, payload)

    def recent(self, limit: int = 50) -> list[OwnerAlert]:
        return list(self.feed)[:limit]

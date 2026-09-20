"""Owner notification interface (SPEC section 12)."""

from __future__ import annotations

from typing import Protocol


class Notifier(Protocol):
    def notify_owner(self, event_type: str, payload: dict) -> None: ...

"""Channel interface (SPEC 3.5, 13). The core engine is channel-agnostic;
the Simulator and WhatsApp Cloud API adapter both implement this so scenario
tests exercise identical logic through either channel."""

from __future__ import annotations

from typing import Protocol


class Channel(Protocol):
    def send_text(self, wa_id: str, text: str) -> None: ...

    def send_image(self, wa_id: str, image_bytes: bytes, caption: str | None = None) -> None: ...

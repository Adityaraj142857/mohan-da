"""In-memory simulator channel (SPEC 13.1). Powers /sim and scenario tests —
no external account needed. Messages are kept in memory per process."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class SimMessage:
    direction: str  # in|out
    kind: str  # text|image
    text: str = ""
    image_bytes: bytes | None = None
    caption: str | None = None
    ts: datetime | None = None


class SimulatorChannel:
    def __init__(self):
        self.inbox: dict[str, list[SimMessage]] = {}

    def _log(self, wa_id: str, msg: SimMessage) -> None:
        self.inbox.setdefault(wa_id, []).append(msg)

    def log_inbound_text(self, wa_id: str, text: str) -> None:
        self._log(wa_id, SimMessage(direction="in", kind="text", text=text, ts=datetime.now()))

    def log_inbound_image(self, wa_id: str) -> None:
        self._log(wa_id, SimMessage(direction="in", kind="image", ts=datetime.now()))

    def send_text(self, wa_id: str, text: str) -> None:
        self._log(wa_id, SimMessage(direction="out", kind="text", text=text, ts=datetime.now()))

    def send_image(self, wa_id: str, image_bytes: bytes, caption: str | None = None) -> None:
        self._log(
            wa_id,
            SimMessage(direction="out", kind="image", image_bytes=image_bytes, caption=caption, ts=datetime.now()),
        )

    def history(self, wa_id: str) -> list[SimMessage]:
        return self.inbox.get(wa_id, [])

    def sent_texts(self, wa_id: str) -> list[str]:
        return [m.text for m in self.history(wa_id) if m.direction == "out" and m.kind == "text"]

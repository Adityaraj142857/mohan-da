"""OCR engine interface (SPEC 4.1, 15.3). Default is RapidOCR (pip-only);
FakeOcrEngine is used in unit/scenario tests so CI never depends on OCR
model quality."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class OcrLine:
    text: str
    confidence: float


@dataclass
class OcrResult:
    lines: list[OcrLine]

    @property
    def full_text(self) -> str:
        return "\n".join(l.text for l in self.lines)

    @property
    def mean_confidence(self) -> float:
        if not self.lines:
            return 0.0
        return sum(l.confidence for l in self.lines) / len(self.lines)


class OcrEngine(Protocol):
    def run(self, image_bytes: bytes) -> OcrResult: ...

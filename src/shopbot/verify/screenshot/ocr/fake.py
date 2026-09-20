"""Test double: no OCR model dependency. Register expected text per image
(by sha256) so tests/CI never depend on real OCR quality (SPEC 15.3)."""

from __future__ import annotations

import hashlib

from shopbot.verify.screenshot.ocr.base import OcrLine, OcrResult


class FakeOcrEngine:
    def __init__(self, default_confidence: float = 0.95):
        self._by_hash: dict[str, str] = {}
        self.default_confidence = default_confidence

    def register(self, image_bytes: bytes, text: str) -> None:
        self._by_hash[hashlib.sha256(image_bytes).hexdigest()] = text

    def run(self, image_bytes: bytes) -> OcrResult:
        key = hashlib.sha256(image_bytes).hexdigest()
        text = self._by_hash.get(key, "")
        lines = [OcrLine(text=line, confidence=self.default_confidence) for line in text.splitlines() if line.strip()]
        return OcrResult(lines=lines)

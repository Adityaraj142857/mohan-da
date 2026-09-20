"""Optional OCR engine: pytesseract, needs the Tesseract system binary
installed separately. Not the default (RapidOCR is pip-only)."""

from __future__ import annotations

import io

from shopbot.verify.screenshot.ocr.base import OcrLine, OcrResult


class TesseractEngine:
    def __init__(self):
        try:
            import pytesseract  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "OCR_ENGINE=tesseract requires: pip install pytesseract, plus the Tesseract binary"
            ) from exc

    def run(self, image_bytes: bytes) -> OcrResult:
        import pytesseract
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        lines = []
        for text, conf in zip(data["text"], data["conf"]):
            text = text.strip()
            if not text:
                continue
            try:
                confidence = max(0.0, float(conf) / 100.0)
            except ValueError:
                confidence = 0.0
            lines.append(OcrLine(text=text, confidence=confidence))
        return OcrResult(lines=lines)

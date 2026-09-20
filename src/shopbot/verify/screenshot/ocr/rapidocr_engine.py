"""Default real OCR engine (SPEC 4.1): RapidOCR, pip-only, no system binary.
Imported lazily so the package only needs `rapidocr-onnxruntime` when
OCR_ENGINE=rapidocr is actually selected (optional extra `.[ocr]`)."""

from __future__ import annotations

import io

from shopbot.verify.screenshot.ocr.base import OcrLine, OcrResult


class RapidOcrEngine:
    def __init__(self):
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:  # pragma: no cover - exercised only when extra installed
            raise RuntimeError(
                "OCR_ENGINE=rapidocr requires the optional 'ocr' extra: pip install -e '.[ocr]'"
            ) from exc
        self._engine = RapidOCR()

    def run(self, image_bytes: bytes) -> OcrResult:
        import numpy as np
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        arr = np.array(img)
        result, _ = self._engine(arr)
        lines = []
        for _box, text, score in result or []:
            lines.append(OcrLine(text=text, confidence=float(score)))
        return OcrResult(lines=lines)

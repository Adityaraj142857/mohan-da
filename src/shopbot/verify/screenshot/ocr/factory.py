from __future__ import annotations

from shopbot.verify.screenshot.ocr.base import OcrEngine
from shopbot.verify.screenshot.ocr.fake import FakeOcrEngine


def make_ocr_engine(engine_name: str) -> OcrEngine:
    if engine_name == "fake":
        return FakeOcrEngine()
    if engine_name == "rapidocr":
        from shopbot.verify.screenshot.ocr.rapidocr_engine import RapidOcrEngine

        return RapidOcrEngine()
    if engine_name == "tesseract":
        from shopbot.verify.screenshot.ocr.tesseract_engine import TesseractEngine

        return TesseractEngine()
    raise ValueError(f"unknown OCR_ENGINE: {engine_name}")

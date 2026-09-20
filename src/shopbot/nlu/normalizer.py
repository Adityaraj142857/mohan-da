"""Normalize free-text order messages (SPEC 9.1-9.2)."""

from __future__ import annotations

import re
import unicodedata

_EMOJI_RE = re.compile(
    "["
    "\U0001f300-\U0001faff"
    "\U00002600-\U000027bf"
    "\U0001f1e6-\U0001f1ff"
    "]+",
    flags=re.UNICODE,
)

# Segment separators: "and", "&", "+", ",", " n ", newline, "aur", "ar", " o "
_SEGMENT_SPLIT_RE = re.compile(
    r"\s*(?:,|&|\+|\n|\band\b|\bn\b|\baur\b|\bar\b|\bo\b)\s*",
    flags=re.IGNORECASE,
)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _EMOJI_RE.sub(" ", text)
    text = text.lower()
    text = text.strip()
    text = re.sub(r"[^\w\s.,&+]", " ", text, flags=re.UNICODE)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n+ *", "\n", text).strip()
    return text


def split_segments(normalized_text: str) -> list[str]:
    segments = [s.strip() for s in _SEGMENT_SPLIT_RE.split(normalized_text)]
    return [s for s in segments if s]

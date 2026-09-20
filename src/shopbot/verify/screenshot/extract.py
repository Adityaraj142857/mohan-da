"""Extract fields from OCR text (SPEC 11.5 step 4). Tolerant to OCR noise —
e.g. '₹' misread as 'T'/'2'/'%'/'Z'."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from dateutil import parser as dateutil_parser

_APP_KEYWORDS = {
    "gpay": ["gpay", "google pay"],
    "phonepe": ["phonepe"],
    "paytm": ["paytm"],
    "bhim": ["bhim"],
}
_SUCCESS_WORDS = ["payment successful", "successful", "completed", "success", "paid"]
_FAILURE_WORDS = ["failed", "pending", "processing", "declined", "cancelled", "canceled"]

_AMOUNT_TOKEN_RE = re.compile(r"[₹tzsT%]?\s?([\d,]+\.\d{2})\b")
_UTR_LABELLED_RE = re.compile(
    r"(?:UPI\s*transaction\s*ID|UPI\s*Ref(?:\s*No\.?)?|UTR)\s*[:\-]?\s*(\d{12})", re.IGNORECASE
)
_UTR_FALLBACK_RE = re.compile(r"\b(\d{12})\b")
_APP_TXN_ID_RE = re.compile(r"\b(T\d{10,})\b")
_VPA_RE = re.compile(r"\b([a-z0-9.\-_]{2,}@[a-z]{2,})\b", re.IGNORECASE)


@dataclass
class ExtractedFields:
    app: str | None = None
    status: str | None = None  # success|failure|unknown
    amount_candidates: list[str] = field(default_factory=list)
    amount_matches_expected: bool = False
    utr: str | None = None
    app_txn_id: str | None = None
    payee_text: str | None = None
    datetime_parsed: object = None  # datetime | None


def _detect_app(lowered: str) -> str | None:
    for app, kws in _APP_KEYWORDS.items():
        if any(kw in lowered for kw in kws):
            return app
    return None


def _detect_status(lowered: str) -> str:
    if any(w in lowered for w in _FAILURE_WORDS):
        return "failure"
    if any(w in lowered for w in _SUCCESS_WORDS):
        return "success"
    return "unknown"


def _expected_amount_present(text: str, expected_rupees: str) -> bool:
    """Expected value check: does the expected payable amount appear as a
    whole numeric token? '114.63' must NOT match inside '1,114.63'."""
    pattern = re.compile(r"(?<!\d)" + re.escape(expected_rupees) + r"(?!\d)")
    for m in re.finditer(r"[\d,]+\.\d{2}", text):
        candidate = m.group(0)
        if candidate.replace(",", "") == expected_rupees:
            # ensure it isn't a substring of a larger comma-grouped number
            start = m.start()
            if start > 0 and text[start - 1] == ",":
                continue
            return True
    return bool(pattern.search(text.replace(",", "")))


def _parse_datetime(text: str):
    candidates = re.findall(
        r"\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4}[,]?\s*\d{1,2}[:.]\d{2}\s*(?:am|pm)?"
        r"|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{2,4}\s+\d{1,2}[:.]\d{2}"
        r"|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}",
        text,
        flags=re.IGNORECASE,
    )
    for cand in candidates:
        try:
            return dateutil_parser.parse(cand, dayfirst=True, fuzzy=True)
        except (ValueError, OverflowError):
            continue
    return None


def extract_fields(ocr_text: str, expected_payable_rupees: str) -> ExtractedFields:
    lowered = ocr_text.lower()
    amount_candidates = [m.group(1) for m in _AMOUNT_TOKEN_RE.finditer(ocr_text)]
    utr_match = _UTR_LABELLED_RE.search(ocr_text) or _UTR_FALLBACK_RE.search(ocr_text)
    app_txn_match = _APP_TXN_ID_RE.search(ocr_text)
    vpa_match = _VPA_RE.search(ocr_text)

    return ExtractedFields(
        app=_detect_app(lowered),
        status=_detect_status(lowered),
        amount_candidates=amount_candidates,
        amount_matches_expected=_expected_amount_present(ocr_text, expected_payable_rupees),
        utr=utr_match.group(1) if utr_match else None,
        app_txn_id=app_txn_match.group(1) if app_txn_match else None,
        payee_text=vpa_match.group(1) if vpa_match else None,
        datetime_parsed=_parse_datetime(ocr_text),
    )

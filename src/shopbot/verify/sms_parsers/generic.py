"""Generic, data-driven bank-SMS parser (SPEC 11.2, 3.7). Bank-specific
modules in `banks/` register a sender regex and may override extraction;
otherwise this generic parser is used. Ship only with synthetic fixtures —
the owner must tune this against their own bank's real (redacted) samples."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from dateutil import parser as dateutil_parser

_NOISE_PATTERNS = [
    r"\botp\b",
    r"do not share",
    r"\bloan\b",
    r"\boffer\b",
    r"\bcashback\b",
    r"\bpromo\b",
    r"congratulations you have won",
]
_CREDIT_WORDS = [r"\bcredited\b", r"\breceived\b", r"\bdeposited\b", r"\bcr\b"]
_DEBIT_WORDS = [r"\bdebited\b", r"\bsent\b", r"\bpaid\b", r"\bwithdrawn\b", r"\bdr\b"]

_AMOUNT_RE = re.compile(r"(?:Rs\.?|INR|₹)\s?([\d,]+(?:\.\d{1,2})?)", re.IGNORECASE)
_UTR_LABELLED_RE = re.compile(
    r"(?:UPI\s*Ref(?:\s*No\.?)?|UPI\s*Txn(?:\s*ID)?|UTR|RRN|Ref\s*No\.?)\s*[:\-]?\s*(\d{12})",
    re.IGNORECASE,
)
_UTR_FALLBACK_RE = re.compile(r"\b(\d{12})\b")
_VPA_RE = re.compile(r"\b([a-z0-9.\-_]{2,}@[a-z]{2,})\b", re.IGNORECASE)
_FROM_NAME_RE = re.compile(r"\b(?:from|by)\s+([A-Z][A-Z .]{2,30})\b")
_LONG_DIGIT_RUN_RE = re.compile(r"\d{6,}")
_DATE_HINT_RE = re.compile(
    r"\d{1,2}[-/][A-Za-z0-9]{2,9}[-/]\d{2,4}(?:,?\s*\d{1,2}[:.]\d{2}\s*(?:am|pm)?)?", re.IGNORECASE
)


@dataclass
class SmsParseResult:
    direction: str  # credit|debit|ignored
    amount_paise: int | None
    utr: str | None
    payer_hint: str | None
    txn_time: datetime | None
    bank: str | None
    raw_redacted: str
    raw_hash: str
    ignored_reason: str | None = None


def _amount_to_paise(amount_str: str) -> int:
    amount_str = amount_str.replace(",", "")
    if "." in amount_str:
        whole, frac = amount_str.split(".")
        frac = (frac + "00")[:2]
    else:
        whole, frac = amount_str, "00"
    return int(whole) * 100 + int(frac)


def redact(text: str, keep: set[str] | None = None) -> str:
    """Mask digit runs of 6+ except any string explicitly in `keep`
    (e.g. the extracted UTR, which we want visible for owner review)."""
    keep = keep or set()

    def _mask(match: re.Match) -> str:
        run = match.group(0)
        if run in keep:
            return run
        if len(run) <= 4:
            return "X" * len(run)
        return "X" * (len(run) - 4) + run[-4:]

    return _LONG_DIGIT_RUN_RE.sub(_mask, text)


def _parse_time(text: str, received_at: datetime) -> datetime:
    m = _DATE_HINT_RE.search(text)
    if not m:
        return received_at
    try:
        dt = dateutil_parser.parse(m.group(0), dayfirst=True, fuzzy=True)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except (ValueError, OverflowError):
        return received_at


def parse_generic(body: str, received_at: datetime, bank_name: str | None = None) -> SmsParseResult:
    lowered = body.lower()

    for pattern in _NOISE_PATTERNS:
        if re.search(pattern, lowered):
            return SmsParseResult(
                direction="ignored",
                amount_paise=None,
                utr=None,
                payer_hint=None,
                txn_time=None,
                bank=bank_name,
                raw_redacted=redact(body),
                raw_hash=hashlib.sha256(body.encode()).hexdigest(),
                ignored_reason="noise",
            )

    is_credit = any(re.search(p, lowered) for p in _CREDIT_WORDS)
    is_debit = any(re.search(p, lowered) for p in _DEBIT_WORDS)
    if is_debit and not is_credit:
        direction = "debit"
    elif is_credit:
        direction = "credit"
    else:
        direction = "ignored"

    amount_match = _AMOUNT_RE.search(body)
    amount_paise = _amount_to_paise(amount_match.group(1)) if amount_match else None

    utr_match = _UTR_LABELLED_RE.search(body) or _UTR_FALLBACK_RE.search(body)
    utr = utr_match.group(1) if utr_match else None

    payer_hint = None
    vpa_match = _VPA_RE.search(body)
    if vpa_match:
        payer_hint = vpa_match.group(1)
    else:
        name_match = _FROM_NAME_RE.search(body)
        if name_match:
            payer_hint = name_match.group(1).strip()

    txn_time = _parse_time(body, received_at)
    raw_hash = hashlib.sha256(body.encode()).hexdigest()
    keep = {utr} if utr else set()

    return SmsParseResult(
        direction=direction,
        amount_paise=amount_paise,
        utr=utr,
        payer_hint=payer_hint,
        txn_time=txn_time,
        bank=bank_name,
        raw_redacted=redact(body, keep=keep),
        raw_hash=raw_hash,
        ignored_reason=None if direction != "ignored" else "no direction keyword matched",
    )

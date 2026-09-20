"""Checks C1-C9 (SPEC 11.5 step 5). Each returns PASS|FAIL|UNKNOWN + reason."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from rapidfuzz import fuzz

from shopbot.verify.screenshot.extract import ExtractedFields
from shopbot.verify.screenshot.forensics import software_looks_edited

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"
PAYEE_FUZZY_THRESHOLD = 85


@dataclass
class CheckResult:
    verdict: str
    reason: str = ""


def check_c1_looks_like_upi(extracted: ExtractedFields, ocr_confidence: float) -> CheckResult:
    if ocr_confidence < 0.5:
        return CheckResult(FAIL, "unreadable image")
    signals = bool(extracted.app or extracted.utr or extracted.amount_candidates)
    return CheckResult(PASS if signals else FAIL, "" if signals else "no UPI-like signals found")


def check_c2_status_success(extracted: ExtractedFields) -> CheckResult:
    if extracted.status == "success":
        return CheckResult(PASS)
    if extracted.status == "failure":
        return CheckResult(FAIL, "failure/pending wording found")
    return CheckResult(UNKNOWN, "status wording not found")


def check_c3_amount_matches(extracted: ExtractedFields) -> CheckResult:
    if extracted.amount_matches_expected:
        return CheckResult(PASS)
    if extracted.amount_candidates:
        return CheckResult(FAIL, f"amount shown: {', '.join(extracted.amount_candidates)}")
    return CheckResult(FAIL, "no amount found")


def check_c4_payee_matches(extracted: ExtractedFields, ocr_text: str, payee_name: str, aliases: list[str]) -> CheckResult:
    names = [payee_name, *aliases]
    lowered = ocr_text.lower()
    for name in names:
        if name.lower() in lowered:
            return CheckResult(PASS)
    best = max((fuzz.partial_ratio(name.lower(), lowered) for name in names), default=0)
    if best >= PAYEE_FUZZY_THRESHOLD:
        return CheckResult(PASS)
    if extracted.payee_text is None and best == 0:
        return CheckResult(UNKNOWN, "no payee text found")
    return CheckResult(FAIL, f"payee not recognised (best match {best})")


def check_c5_timestamp_window(
    extracted: ExtractedFields, order_created_at: datetime, now: datetime
) -> CheckResult:
    if extracted.datetime_parsed is None:
        return CheckResult(UNKNOWN, "no timestamp found")
    dt = extracted.datetime_parsed
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=order_created_at.tzinfo)
    lower = order_created_at - timedelta(minutes=2)
    upper = now + timedelta(minutes=5)
    if lower <= dt <= upper:
        return CheckResult(PASS)
    return CheckResult(FAIL, f"timestamp {dt.isoformat()} outside expected window")


def check_c6_utr_present(extracted: ExtractedFields) -> CheckResult:
    return CheckResult(PASS if extracted.utr else UNKNOWN, "" if extracted.utr else "no UTR found")


def check_c7_utr_not_reused(utr_already_used_elsewhere: bool) -> CheckResult:
    return CheckResult(FAIL if utr_already_used_elsewhere else PASS)


def check_c8_not_duplicate_image(is_duplicate: bool) -> CheckResult:
    return CheckResult(FAIL if is_duplicate else PASS)


def check_c9_metadata_advisory(exif_software: str | None) -> CheckResult:
    if software_looks_edited(exif_software):
        return CheckResult(UNKNOWN, f"EXIF Software suggests editing: {exif_software}")
    return CheckResult(UNKNOWN, "advisory only")

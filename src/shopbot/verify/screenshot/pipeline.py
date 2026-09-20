"""Screenshot verification pipeline (SPEC 11.5). A screenshot is a filter +
matching key + owner-assist — never the sole source of truth for PAID
(SPEC 3.1). `verify_screenshot` is the single entry point used by every
channel (WhatsApp, pay-page upload, simulator)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from shopbot.clock import Clock
from shopbot.config import Settings
from shopbot.models import EventLog, Order, Screenshot
from shopbot.money import paise_to_rupees_str
from shopbot.verify import matcher
from shopbot.verify.screenshot import checks as chk
from shopbot.verify.screenshot.extract import extract_fields
from shopbot.verify.screenshot.forensics import phash_distance, validate_and_fingerprint
from shopbot.verify.screenshot.ocr.base import OcrEngine

MAX_UNREADABLE_RETRIES = 2
DUPLICATE_PHASH_DISTANCE = 4


@dataclass
class ScreenshotOutcome:
    verdict: str
    message_key: str  # which template the conversation layer should send
    screenshot_id: str | None = None
    checks: dict = field(default_factory=dict)


def _find_duplicate(session: Session, order: Order, sha256: str, phash: str | None, utr: str | None) -> str | None:
    others = session.scalars(select(Screenshot).where(Screenshot.order_id != order.id)).all()
    for shot in others:
        if shot.sha256 == sha256:
            return "sha256"
        if phash and shot.phash:
            try:
                if phash_distance(phash, shot.phash) <= DUPLICATE_PHASH_DISTANCE:
                    return "phash"
            except ValueError:
                pass
        if utr and (shot.extracted or {}).get("utr") == utr:
            return "utr"
    return None


def _save_media(media_dir: Path, order_code: str, image_bytes: bytes, sha256: str) -> str:
    media_dir.mkdir(parents=True, exist_ok=True)
    path = media_dir / f"{order_code}_{sha256[:12]}.jpg"
    path.write_bytes(image_bytes)
    return str(path)


def verify_screenshot(
    session: Session,
    settings: Settings,
    order: Order,
    image_bytes: bytes,
    source: str,
    ocr_engine: OcrEngine,
    clock: Clock,
    media_dir: Path,
    notifier=None,
) -> ScreenshotOutcome:
    if order.status == "PAID":
        return ScreenshotOutcome(verdict="PAID", message_key="already_confirmed")

    validation = validate_and_fingerprint(image_bytes)
    if not validation.ok:
        return ScreenshotOutcome(verdict="INVALID", message_key="ask_clearer_image", checks={"reason": validation.reason})

    ocr_result = ocr_engine.run(image_bytes)
    if ocr_result.mean_confidence < 0.5 or not ocr_result.lines:
        prior_unreadable = session.scalars(
            select(Screenshot).where(Screenshot.order_id == order.id, Screenshot.verdict == "UNREADABLE")
        ).all()
        if len(prior_unreadable) >= MAX_UNREADABLE_RETRIES:
            order.payment_state = "NEEDS_OWNER"
            if notifier:
                notifier.notify_owner("screenshot_unreadable_repeated", {"order_code": order.code})
            return ScreenshotOutcome(verdict="NEEDS_OWNER", message_key="claim_needs_owner")
        _persist_screenshot(session, order, source, image_bytes, validation, {}, {}, None, "UNREADABLE", media_dir, clock)
        return ScreenshotOutcome(verdict="UNREADABLE", message_key="ask_clearer_image")

    expected_rupees = paise_to_rupees_str(order.payable_paise)
    extracted = extract_fields(ocr_result.full_text, expected_rupees)

    duplicate_kind = _find_duplicate(session, order, validation.sha256, validation.phash, extracted.utr)

    checks: dict[str, dict] = {}
    checks["C1"] = vars(chk.check_c1_looks_like_upi(extracted, ocr_result.mean_confidence))
    checks["C2"] = vars(chk.check_c2_status_success(extracted))
    checks["C3"] = vars(chk.check_c3_amount_matches(extracted))
    checks["C4"] = vars(
        chk.check_c4_payee_matches(extracted, ocr_result.full_text, settings.payee_name, settings.payee_aliases_list())
    )
    checks["C5"] = vars(chk.check_c5_timestamp_window(extracted, order.created_at, clock.now()))
    checks["C6"] = vars(chk.check_c6_utr_present(extracted))
    checks["C7"] = vars(chk.check_c7_utr_not_reused(duplicate_kind == "utr"))
    checks["C8"] = vars(chk.check_c8_not_duplicate_image(duplicate_kind in ("sha256", "phash")))
    checks["C9"] = vars(chk.check_c9_metadata_advisory(validation.exif_software))

    extracted_dict = vars(extracted).copy()
    dt = extracted_dict.get("datetime_parsed")
    extracted_dict["datetime_parsed"] = dt.isoformat() if isinstance(dt, datetime) else None

    screenshot_id = _persist_screenshot(
        session, order, source, image_bytes, validation, extracted_dict, checks, None, "PENDING", media_dir, clock
    )

    report = {"extracted": {"utr": extracted.utr}, "verdict": "PENDING_BANK"}
    bank_verdict = matcher.on_new_screenshot_report(session, order, report, clock, notifier=notifier)

    screenshot = session.get(Screenshot, screenshot_id)

    if bank_verdict == "PAID":
        screenshot.verdict = "PAID"
        screenshot.bank_cross_check = "BANK_CONFIRMED"
        return ScreenshotOutcome(verdict="PAID", message_key="paid", screenshot_id=screenshot_id, checks=checks)

    if bank_verdict == "NEEDS_OWNER":
        screenshot.verdict = "NEEDS_OWNER"
        screenshot.bank_cross_check = "BANK_MISMATCH"
        return ScreenshotOutcome(verdict="NEEDS_OWNER", message_key="claim_needs_owner", screenshot_id=screenshot_id, checks=checks)

    if bank_verdict == "REJECTED_CLAIM":
        _flag_fraud(session, order, "duplicate_utr")
        screenshot.verdict = "REJECTED_CLAIM"
        screenshot.bank_cross_check = "BANK_MISMATCH"
        return ScreenshotOutcome(verdict="REJECTED_CLAIM", message_key="claim_rejected", screenshot_id=screenshot_id, checks=checks)

    hard_fail_ids = [cid for cid, c in checks.items() if cid != "C9" and c["verdict"] == "FAIL"]
    screenshot.bank_cross_check = "BANK_PENDING"

    if hard_fail_ids:
        if any(cid in ("C7", "C8") for cid in hard_fail_ids):
            _flag_fraud(session, order, "duplicate_screenshot")
        order.payment_state = "REJECTED_CLAIM"
        screenshot.verdict = "REJECTED_CLAIM"
        if notifier:
            notifier.notify_owner(
                "screenshot_rejected", {"order_code": order.code, "failed_checks": hard_fail_ids}
            )
        return ScreenshotOutcome(verdict="REJECTED_CLAIM", message_key="claim_rejected", screenshot_id=screenshot_id, checks=checks)

    if settings.screenshot_policy == "auto_approve_if_strong":
        strong = (
            all(checks[c]["verdict"] == "PASS" for c in ["C1", "C2", "C3", "C6", "C7", "C8"])
            and order.payable_paise <= settings.auto_approve_max_paise
        )
        if strong:
            from shopbot.orders.service import mark_paid

            order.payment_state = "PAID_UNVERIFIED"
            mark_paid(session, order, paid_via="screenshot_auto", clock=clock)
            screenshot.verdict = "PAID_UNVERIFIED"
            session.add(EventLog(type="paid_unverified", order_id=order.id, payload={}))
            if notifier:
                notifier.notify_owner("paid_unverified_reconcile", {"order_code": order.code})
            return ScreenshotOutcome(verdict="PAID_UNVERIFIED", message_key="paid", screenshot_id=screenshot_id, checks=checks)

    if settings.bank_signal == "none":
        order.payment_state = "NEEDS_OWNER"
        screenshot.verdict = "NEEDS_OWNER"
        if notifier:
            notifier.notify_owner("needs_owner_review", {"order_code": order.code})
        return ScreenshotOutcome(verdict="NEEDS_OWNER", message_key="claim_needs_owner", screenshot_id=screenshot_id, checks=checks)

    order.payment_state = "PENDING_BANK"
    screenshot.verdict = "PENDING_BANK"
    return ScreenshotOutcome(verdict="PENDING_BANK", message_key="claim_pending", screenshot_id=screenshot_id, checks=checks)


def _flag_fraud(session: Session, order: Order, reason: str) -> None:
    customer = order.customer
    customer.fraud_flags = (customer.fraud_flags or 0) + 1
    session.add(EventLog(type="fraud_flag", order_id=order.id, customer_id=customer.id, payload={"reason": reason}))


def _persist_screenshot(
    session: Session,
    order: Order,
    source: str,
    image_bytes: bytes,
    validation,
    extracted: dict,
    checks: dict,
    bank_cross_check: str | None,
    verdict: str,
    media_dir: Path,
    clock: Clock,
) -> str:
    file_path = _save_media(media_dir, order.code, validation.normalized_bytes or image_bytes, validation.sha256)
    screenshot = Screenshot(
        order_id=order.id,
        source=source,
        file_path=file_path,
        sha256=validation.sha256,
        phash=validation.phash,
        ocr_text=None,
        extracted=extracted,
        checks=checks,
        bank_cross_check=bank_cross_check,
        verdict=verdict,
        created_at=clock.now(),
    )
    session.add(screenshot)
    session.flush()
    return screenshot.id

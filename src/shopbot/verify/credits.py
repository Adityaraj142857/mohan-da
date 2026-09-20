"""Bank-credit ingestion: sender filter, parse, dedupe, store (SPEC 11.1-11.2)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from shopbot.clock import Clock
from shopbot.models import Credit, EventLog, Order
from shopbot.verify.sms_parsers.registry import parse_with_registry


@dataclass
class IngestResult:
    status: str  # stored|duplicate|ignored
    credit: Credit | None
    parser_used: str | None = None


def ingest_sms(
    session: Session,
    sender: str,
    body: str,
    received_at: datetime,
    allowed_sender_regex: str,
    source: str = "sms",
) -> IngestResult:
    if not re.match(allowed_sender_regex, sender or ""):
        return IngestResult(status="ignored", credit=None)

    parsed, parser_name = parse_with_registry(sender, body, received_at)

    if parsed.direction == "ignored":
        return IngestResult(status="ignored", credit=None, parser_used=parser_name)

    existing = session.scalar(select(Credit).where(Credit.raw_hash == parsed.raw_hash))
    if existing:
        return IngestResult(status="duplicate", credit=existing, parser_used=parser_name)
    if parsed.utr:
        existing_by_utr = session.scalar(select(Credit).where(Credit.utr == parsed.utr))
        if existing_by_utr:
            return IngestResult(status="duplicate", credit=existing_by_utr, parser_used=parser_name)

    credit = Credit(
        source=source,
        sender=sender,
        raw_redacted=parsed.raw_redacted,
        raw_hash=parsed.raw_hash,
        amount_paise=parsed.amount_paise or 0,
        utr=parsed.utr,
        payer_hint=parsed.payer_hint,
        bank=parsed.bank,
        direction=parsed.direction,
        txn_time=parsed.txn_time,
        received_at=received_at,
        status="UNMATCHED",
    )
    session.add(credit)
    session.flush()
    session.add(EventLog(type="credit_ingested", payload={"credit_id": credit.id, "direction": credit.direction}))
    return IngestResult(status="stored", credit=credit, parser_used=parser_name)


def ingest_and_match(
    session: Session,
    sender: str,
    body: str,
    received_at: datetime,
    allowed_sender_regex: str,
    clock: Clock,
    grace_minutes: int,
    overpay_tolerance_paise: int,
    notifier=None,
    source: str = "sms",
) -> tuple[IngestResult, Order | None]:
    """Ingest one SMS and immediately run the matcher (SPEC 11.1 webhook
    contract). Returns the ingest result and the order that just got PAID by
    this credit, if any, so the caller can push a "paid" message."""
    from shopbot.verify.matcher import on_new_credit

    ingest = ingest_sms(session, sender, body, received_at, allowed_sender_regex, source=source)
    if ingest.status != "stored" or ingest.credit is None:
        return ingest, None

    on_new_credit(
        session,
        ingest.credit,
        clock,
        grace_minutes=grace_minutes,
        overpay_tolerance_paise=overpay_tolerance_paise,
        notifier=notifier,
    )
    matched_order = None
    if ingest.credit.matched_order_id:
        matched_order = session.get(Order, ingest.credit.matched_order_id)
        if matched_order and matched_order.status != "PAID":
            matched_order = None
    return ingest, matched_order


def add_manual_credit(
    session: Session, amount_paise: int, utr: str | None, txn_time: datetime, note: str = ""
) -> Credit:
    import hashlib
    import uuid

    raw = f"manual:{uuid.uuid4().hex}:{note}"
    credit = Credit(
        source="manual",
        sender="manual",
        raw_redacted=note or "manual entry",
        raw_hash=hashlib.sha256(raw.encode()).hexdigest(),
        amount_paise=amount_paise,
        utr=utr,
        direction="credit",
        txn_time=txn_time,
        status="UNMATCHED",
    )
    session.add(credit)
    session.flush()
    session.add(EventLog(type="credit_manual_added", payload={"credit_id": credit.id}))
    return credit

"""Matching engine (SPEC 11.4). Runs on every new credit and every
screenshot-state change, inside a DB transaction. Idempotent: a credit
matches at most one order; an order at most one credit."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from shopbot.clock import Clock
from shopbot.models import Credit, EventLog, Order
from shopbot.orders.service import mark_paid

CANDIDATE_PAYMENT_STATES = ("NONE", "CLAIMED", "PENDING_BANK", "NEEDS_OWNER")
NEAR_MISS_MAX_DIFF_PAISE = 5000  # ₹50 — bound for flagging a "wrong amount" near-miss (SPEC 11.4/11.7)


def _candidate_orders(session: Session, credit: Credit, grace_minutes: int, overpay_tolerance: int) -> list[Order]:
    candidates = []
    orders = session.scalars(
        select(Order).where(
            Order.payment_state.in_(CANDIDATE_PAYMENT_STATES),
            Order.status.in_(["AWAITING_PAYMENT", "EXPIRED"]),
        )
    ).all()
    txn_time = credit.txn_time
    for order in orders:
        amount_ok = credit.amount_paise == order.payable_paise or (
            0 <= credit.amount_paise - order.payable_paise <= overpay_tolerance
        )
        if not amount_ok:
            continue
        if txn_time is None:
            candidates.append(order)
            continue
        window_end = (order.expires_at or order.created_at) + timedelta(minutes=grace_minutes)
        if order.created_at <= txn_time <= window_end:
            candidates.append(order)
    return candidates


def on_new_credit(
    session: Session,
    credit: Credit,
    clock: Clock,
    grace_minutes: int = 30,
    overpay_tolerance_paise: int = 0,
    notifier=None,
) -> None:
    if credit.direction != "credit" or credit.status != "UNMATCHED":
        return

    # If a screenshot already carries this credit's UTR, prefer that order.
    preferred_order = None
    if credit.utr:
        from shopbot.models import Screenshot

        shots = session.scalars(select(Screenshot)).all()
        for shot in shots:
            if (shot.extracted or {}).get("utr") == credit.utr:
                preferred_order = session.get(Order, shot.order_id)
                break

    candidates = [preferred_order] if preferred_order else _candidate_orders(
        session, credit, grace_minutes, overpay_tolerance_paise
    )
    candidates = [c for c in candidates if c is not None]

    if len(candidates) == 1:
        order = candidates[0]
        was_expired = order.status == "EXPIRED"
        credit.status = "MATCHED"
        credit.matched_order_id = order.id
        credit.match_method = "utr" if (credit.utr and preferred_order) else "amount_unique"
        if was_expired:
            order.status = "AWAITING_PAYMENT"  # legal hop before PAID, logged below
        mark_paid(session, order, paid_via="bank_sms", clock=clock, credit_id=credit.id)
        if was_expired:
            order.payment_state = "NEEDS_OWNER"
            order.status = "AWAITING_PAYMENT"
            session.add(EventLog(type="late_credit", order_id=order.id, payload={"credit_id": credit.id}))
            if notifier:
                notifier.notify_owner("late_payment", {"order_code": order.code, "credit_id": credit.id})
            return
        if notifier:
            notifier.notify_owner("order_paid", {"order_code": order.code})
    elif len(candidates) > 1:
        for order in candidates:
            order.payment_state = "NEEDS_OWNER"
        session.add(
            EventLog(
                type="ambiguous_match",
                payload={"credit_id": credit.id, "order_codes": [o.code for o in candidates]},
            )
        )
        if notifier:
            notifier.notify_owner(
                "needs_owner_ambiguous", {"credit_id": credit.id, "orders": [o.code for o in candidates]}
            )
    else:
        # No exact match. Credit sits UNMATCHED (owner can dismiss it later,
        # e.g. the owner's own personal income) UNLESS there is exactly one
        # pending order that is plausibly the intended target: active in the
        # same time window and off by a bounded amount (SPEC 11.4/11.7 —
        # "if a near-miss order exists"). We deliberately do NOT flag every
        # unrelated pending order in the shop just because one credit didn't
        # match anything.
        pending = session.scalars(
            select(Order).where(
                Order.payment_state.in_(CANDIDATE_PAYMENT_STATES),
                Order.status == "AWAITING_PAYMENT",
            )
        ).all()
        near_misses = []
        for order in pending:
            if order.payable_paise == credit.amount_paise:
                continue
            if credit.txn_time is not None:
                window_end = (order.expires_at or order.created_at) + timedelta(minutes=grace_minutes)
                if not (order.created_at <= credit.txn_time <= window_end):
                    continue
            diff = abs(order.payable_paise - credit.amount_paise)
            if diff <= NEAR_MISS_MAX_DIFF_PAISE:
                near_misses.append((diff, order))

        if len(near_misses) == 1:
            _, order = near_misses[0]
            order.payment_state = "NEEDS_OWNER"
            session.add(
                EventLog(
                    type="near_miss_amount",
                    order_id=order.id,
                    payload={"expected": order.payable_paise, "got": credit.amount_paise},
                )
            )
            if notifier:
                notifier.notify_owner(
                    "wrong_amount",
                    {"order_code": order.code, "expected": order.payable_paise, "got": credit.amount_paise},
                )


def on_new_screenshot_report(session: Session, order: Order, report: dict, clock: Clock, notifier=None) -> str:
    """Apply the decisive bank cross-check for a screenshot (SPEC 11.4).
    Returns the resulting verdict string; caller (screenshot pipeline)
    already computed hard-fail checks and passes bank_cross_check here."""
    utr = report.get("extracted", {}).get("utr")
    if utr:
        credit = session.scalar(select(Credit).where(Credit.utr == utr))
        if credit:
            if credit.status == "MATCHED" and credit.matched_order_id != order.id:
                order.payment_state = "NEEDS_OWNER"
                session.add(
                    EventLog(
                        type="duplicate_utr",
                        order_id=order.id,
                        payload={"utr": utr, "other_order": credit.matched_order_id},
                    )
                )
                if notifier:
                    notifier.notify_owner("fraud_duplicate_utr", {"order_code": order.code, "utr": utr})
                return "REJECTED_CLAIM"
            if credit.amount_paise == order.payable_paise:
                credit.status = "MATCHED"
                credit.matched_order_id = order.id
                credit.match_method = "utr"
                mark_paid(session, order, paid_via="utr", clock=clock, credit_id=credit.id)
                if notifier:
                    notifier.notify_owner("order_paid", {"order_code": order.code})
                return "PAID"
            order.payment_state = "NEEDS_OWNER"
            session.add(
                EventLog(
                    type="amount_mismatch",
                    order_id=order.id,
                    payload={"expected": order.payable_paise, "bank_amount": credit.amount_paise},
                )
            )
            if notifier:
                notifier.notify_owner(
                    "needs_owner_amount_mismatch",
                    {"order_code": order.code, "expected": order.payable_paise, "bank_amount": credit.amount_paise},
                )
            return "NEEDS_OWNER"
    return report.get("verdict", "PENDING_BANK")

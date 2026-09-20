"""Order lifecycle: creation, pricing, confirmation, payment, and the order
status state machine (SPEC 6, 7, 11.6). Illegal transitions raise
`IllegalTransition`."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from shopbot.clock import Clock
from shopbot.menu.pricing import PricedLine, delivery_fee_paise, subtotal_paise, total_paise
from shopbot.models import Customer, EventLog, Order, OrderItem
from shopbot.nlu.parser import ParsedLine
from shopbot.orders.codes import new_order_code
from shopbot.payments.paypage import new_pay_token
from shopbot.payments.unique_amount import allocate_unique_paise


class IllegalTransition(Exception):
    pass


ORDER_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"AWAITING_PAYMENT", "CANCELLED"},
    "AWAITING_PAYMENT": {"PAID", "EXPIRED", "CANCELLED"},
    "PAID": {"PREPARING", "CANCELLED"},
    "PREPARING": {"READY", "CANCELLED"},
    "READY": {"OUT_FOR_DELIVERY", "COMPLETED", "CANCELLED"},
    "OUT_FOR_DELIVERY": {"COMPLETED", "CANCELLED"},
    "EXPIRED": {"PAID", "AWAITING_PAYMENT"},  # late credit -> owner approve; or explicit re-open
    "COMPLETED": set(),
    "CANCELLED": set(),
}


def validate_transition(current: str, new: str) -> None:
    allowed = ORDER_TRANSITIONS.get(current, set())
    if new not in allowed:
        raise IllegalTransition(f"cannot move order from {current} to {new}")


def transition_order(session: Session, order: Order, new_status: str, reason: str = "") -> None:
    validate_transition(order.status, new_status)
    old = order.status
    order.status = new_status
    session.add(
        EventLog(
            type="order_status_changed",
            order_id=order.id,
            payload={"from": old, "to": new_status, "reason": reason},
        )
    )


def get_or_create_customer(session: Session, wa_id: str, name: str | None = None) -> Customer:
    customer = session.scalar(select(Customer).where(Customer.wa_id == wa_id))
    if customer is None:
        customer = Customer(wa_id=wa_id, name=name)
        session.add(customer)
        session.flush()
    return customer


@dataclass
class DraftTotals:
    subtotal_paise: int
    delivery_fee_paise: int
    total_paise: int


def compute_draft_totals(
    lines: list[ParsedLine],
    fulfilment: str | None,
    hostel: str | None,
    default_fee_paise: int,
    per_hostel_fee_paise: dict[str, int] | None = None,
) -> DraftTotals:
    priced = [PricedLine(name=l.name, unit_price_paise=l.unit_price_paise, qty=l.qty) for l in lines]
    sub = subtotal_paise(priced)
    fee = delivery_fee_paise(fulfilment or "takeout", hostel, default_fee_paise, per_hostel_fee_paise)
    return DraftTotals(subtotal_paise=sub, delivery_fee_paise=fee, total_paise=total_paise(sub, fee))


def create_draft_order(session: Session, customer: Customer) -> Order:
    existing_codes = set(session.scalars(select(Order.code)))
    order = Order(code=new_order_code(existing_codes), customer_id=customer.id, status="DRAFT")
    session.add(order)
    session.flush()
    return order


def set_order_lines(session: Session, order: Order, lines: list[ParsedLine]) -> None:
    for existing in list(order.items):
        session.delete(existing)
    order.items = []
    session.flush()
    for line in lines:
        session.add(
            OrderItem(
                order_id=order.id,
                item_id=line.item_id,
                name_snapshot=line.name,
                unit_price_paise=line.unit_price_paise,
                qty=line.qty,
                line_total_paise=line.unit_price_paise * line.qty,
                note=line.note,
            )
        )
    session.flush()
    session.refresh(order, attribute_names=["items"])


def _used_unique_paise_for_total(session: Session, base_total_paise: int) -> set[int]:
    pending = session.scalars(
        select(Order).where(
            Order.status.in_(["AWAITING_PAYMENT"]),
            Order.total_paise == base_total_paise,
        )
    ).all()
    return {o.unique_adjust_paise for o in pending}


def confirm_and_price_order(
    session: Session,
    order: Order,
    fulfilment: str,
    hostel: str | None,
    room: str | None,
    default_fee_paise: int,
    unique_mode: str,
    unique_paise_max: int,
    payment_ttl_min: int,
    clock: Clock,
    per_hostel_fee_paise: dict[str, int] | None = None,
) -> None:
    """Recompute totals from persisted order_items, allocate the unique
    amount, generate a pay token, and move the order to AWAITING_PAYMENT."""
    persisted_items = session.scalars(select(OrderItem).where(OrderItem.order_id == order.id)).all()
    lines = [
        PricedLine(name=i.name_snapshot, unit_price_paise=i.unit_price_paise, qty=i.qty)
        for i in persisted_items
    ]
    sub = subtotal_paise(lines)
    fee = delivery_fee_paise(fulfilment, hostel, default_fee_paise, per_hostel_fee_paise)
    total = total_paise(sub, fee)

    unique_adjust = 0
    if unique_mode != "off":
        used = _used_unique_paise_for_total(session, total)
        allocated = allocate_unique_paise(used, unique_paise_max)
        if allocated is None:
            allocated = allocate_unique_paise(used, unique_paise_max * 10) or 0
        unique_adjust = allocated

    from shopbot.menu.pricing import payable_paise

    payable = payable_paise(total, unique_adjust, unique_mode)

    order.fulfilment_type = fulfilment
    order.hostel = hostel
    order.room = room
    order.subtotal_paise = sub
    order.delivery_fee_paise = fee
    order.total_paise = total
    order.unique_adjust_paise = unique_adjust
    order.payable_paise = payable
    order.pay_token = new_pay_token()
    order.created_at = clock.now()
    order.expires_at = clock.now() + timedelta(minutes=payment_ttl_min)

    transition_order(session, order, "AWAITING_PAYMENT", reason="customer confirmed")


def mark_paid(session: Session, order: Order, paid_via: str, clock: Clock, credit_id: str | None = None) -> None:
    if order.status not in ("AWAITING_PAYMENT", "EXPIRED"):
        raise IllegalTransition(f"cannot mark {order.status} order as paid")
    validate_transition(order.status, "PAID")
    order.status = "PAID"
    order.payment_state = "VERIFIED"
    order.paid_at = clock.now()
    order.paid_via = paid_via
    order.matched_credit_id = credit_id
    session.add(
        EventLog(
            type="order_paid",
            order_id=order.id,
            payload={"via": paid_via, "credit_id": credit_id},
        )
    )


def cancel_order(session: Session, order: Order, reason: str) -> None:
    transition_order(session, order, "CANCELLED", reason=reason)

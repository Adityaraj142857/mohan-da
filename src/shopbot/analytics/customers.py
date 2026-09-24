"""Customer analytics: profiles, segments, and intelligence signals.

Uses existing Customer + Order + OrderItem data only.
No LLM, no external service \u2014 pure deterministic analytics.

Segments:
  New Customer    \u2014 fewer than MIN_ORDERS_FOR_SEGMENT paid orders
  Frequent Buyer  \u2014 >= FREQUENT_ORDERS_PER_WEEK orders/week (rolling 4 weeks)
  High-Value      \u2014 AOV >= HIGH_VALUE_AOV_PAISE
  Dormant         \u2014 no order in DORMANT_DAYS days
  Occasional      \u2014 recurring but not frequent
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from shopbot.analytics.constants import (
    DORMANT_DAYS,
    FREQUENT_ORDERS_PER_WEEK,
    HIGH_VALUE_AOV_PAISE,
    MIN_ORDERS_FOR_PERSONALIZATION,
    MIN_ORDERS_FOR_SEGMENT,
)
from shopbot.clock import IST
from shopbot.models import Customer, Order, OrderItem
from shopbot.money import format_inr

PAID_STATUSES = ("PAID", "PREPARING", "READY", "OUT_FOR_DELIVERY", "COMPLETED")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CustomerProfile:
    customer_id: str
    wa_id: str
    name: str | None
    segment: str
    total_orders: int
    total_spend_paise: int
    total_spend_display: str
    aov_paise: int
    aov_display: str
    last_order_date: date | None
    days_since_last_order: int | None
    favourite_items: list[str] = field(default_factory=list)   # top 3 items
    frequent_pairs: list[tuple[str, str]] = field(default_factory=list)  # top pairs
    typical_hour_ist: int | None = None       # most common order hour
    typical_hour_label: str | None = None
    has_enough_history: bool = False
    personalized_suggestion: str | None = None


@dataclass
class CustomerSummaryRow:
    customer_id: str
    wa_id: str
    name: str | None
    segment: str
    total_orders: int
    total_spend_display: str
    aov_display: str
    last_order_date: str
    favourite_item: str | None
    fraud_flags: int
    blocked: bool


# ---------------------------------------------------------------------------
# Segmentation
# ---------------------------------------------------------------------------


def segment_customer(
    total_paid_orders: int,
    total_spend_paise: int,
    last_order_date: date | None,
    orders_per_week_4w: float,
) -> str:
    """Deterministic, rules-based segmentation."""
    if total_paid_orders < MIN_ORDERS_FOR_SEGMENT:
        return "New Customer"

    today = datetime.now(IST).date()
    if last_order_date and (today - last_order_date).days >= DORMANT_DAYS:
        return "Dormant Customer"

    aov = total_spend_paise // total_paid_orders if total_paid_orders else 0

    if orders_per_week_4w >= FREQUENT_ORDERS_PER_WEEK:
        return "Frequent Buyer"

    if aov >= HIGH_VALUE_AOV_PAISE:
        return "High-Value Customer"

    return "Occasional Buyer"


# ---------------------------------------------------------------------------
# Core profile computation
# ---------------------------------------------------------------------------


def get_customer_profile(session: Session, customer_id: str) -> CustomerProfile | None:
    customer = session.get(Customer, customer_id)
    if customer is None:
        return None

    paid_orders = [
        o for o in customer.orders
        if o.status in PAID_STATUSES
    ]
    paid_orders.sort(key=lambda o: o.created_at or datetime.min.replace(tzinfo=IST))

    total_spend = sum(o.payable_paise for o in paid_orders)
    aov = total_spend // len(paid_orders) if paid_orders else 0
    last_order: date | None = None
    days_since: int | None = None

    if paid_orders:
        last_dt = paid_orders[-1].created_at
        if last_dt:
            last_order = last_dt.astimezone(IST).date()
            days_since = (datetime.now(IST).date() - last_order).days

    # Orders per week in the last 4 weeks
    four_weeks_ago = datetime.now(IST) - timedelta(weeks=4)
    recent = [
        o for o in paid_orders
        if o.created_at and o.created_at.astimezone(IST) >= four_weeks_ago
    ]
    orders_per_week_4w = len(recent) / 4.0

    segment = segment_customer(
        total_paid_orders=len(paid_orders),
        total_spend_paise=total_spend,
        last_order_date=last_order,
        orders_per_week_4w=orders_per_week_4w,
    )

    has_enough = len(paid_orders) >= MIN_ORDERS_FOR_PERSONALIZATION

    # Favourite items
    item_counter: Counter[str] = Counter()
    pair_counter: Counter[tuple[str, str]] = Counter()
    hour_counter: Counter[int] = Counter()

    for order in paid_orders:
        names = sorted(i.name_snapshot for i in order.items)
        for item in order.items:
            item_counter[item.name_snapshot] += item.qty
        # pairs
        for j in range(len(names)):
            for k in range(j + 1, len(names)):
                pair_counter[(names[j], names[k])] += 1
        # hour
        if order.created_at:
            h = order.created_at.astimezone(IST).hour
            hour_counter[h] += 1

    fav_items = [name for name, _ in item_counter.most_common(3)]
    top_pairs = [pair for pair, _ in pair_counter.most_common(2)]

    typical_hour: int | None = None
    typical_hour_label: str | None = None
    if hour_counter:
        typical_hour = hour_counter.most_common(1)[0][0]
        typical_hour_label = _hour_label(typical_hour)

    # Simple personalised suggestion text
    suggestion: str | None = None
    if has_enough and fav_items:
        if top_pairs:
            a, b = top_pairs[0]
            if len(fav_items) >= 2:
                suggestion = f"Your usual {fav_items[0]}? Customers like you often add {fav_items[1]}."
            else:
                suggestion = f"Want to add a {b} with your {a}?"
        else:
            suggestion = f"Your favourite {fav_items[0]} is on the menu!"

    return CustomerProfile(
        customer_id=customer.id,
        wa_id=customer.wa_id,
        name=customer.name,
        segment=segment,
        total_orders=len(paid_orders),
        total_spend_paise=total_spend,
        total_spend_display=format_inr(total_spend),
        aov_paise=aov,
        aov_display=format_inr(aov),
        last_order_date=last_order,
        days_since_last_order=days_since,
        favourite_items=fav_items,
        frequent_pairs=top_pairs,
        typical_hour_ist=typical_hour,
        typical_hour_label=typical_hour_label,
        has_enough_history=has_enough,
        personalized_suggestion=suggestion,
    )


def get_all_customer_summaries(session: Session) -> list[CustomerSummaryRow]:
    """Return a lightweight summary row for every customer (for the list page)."""
    customers = session.scalars(select(Customer)).all()
    rows: list[CustomerSummaryRow] = []

    for customer in customers:
        paid_orders = [o for o in customer.orders if o.status in PAID_STATUSES]
        total_spend = sum(o.payable_paise for o in paid_orders)
        aov = total_spend // len(paid_orders) if paid_orders else 0

        last_order_date: date | None = None
        if paid_orders:
            last_dt = max((o.created_at for o in paid_orders if o.created_at), default=None)
            if last_dt:
                last_order_date = last_dt.astimezone(IST).date()

        # Favourite item
        item_counter: Counter[str] = Counter()
        for order in paid_orders:
            for item in order.items:
                item_counter[item.name_snapshot] += item.qty
        fav = item_counter.most_common(1)[0][0] if item_counter else None

        # Last order date display
        if last_order_date:
            days_since = (datetime.now(IST).date() - last_order_date).days
            if days_since == 0:
                last_str = "Today"
            elif days_since == 1:
                last_str = "Yesterday"
            else:
                last_str = f"{days_since} days ago"
        else:
            last_str = "Never"

        # Quick segment
        four_weeks_ago = datetime.now(IST) - timedelta(weeks=4)
        recent = [
            o for o in paid_orders
            if o.created_at and o.created_at.astimezone(IST) >= four_weeks_ago
        ]
        segment = segment_customer(
            total_paid_orders=len(paid_orders),
            total_spend_paise=total_spend,
            last_order_date=last_order_date,
            orders_per_week_4w=len(recent) / 4.0,
        )

        rows.append(CustomerSummaryRow(
            customer_id=customer.id,
            wa_id=customer.wa_id,
            name=customer.name,
            segment=segment,
            total_orders=len(paid_orders),
            total_spend_display=format_inr(total_spend),
            aov_display=format_inr(aov),
            last_order_date=last_str,
            favourite_item=fav,
            fraud_flags=customer.fraud_flags,
            blocked=customer.blocked,
        ))

    return rows


def _hour_label(h: int) -> str:
    def _fmt(hr: int) -> str:
        period = "AM" if hr < 12 else "PM"
        hr12 = hr % 12 or 12
        return f"{hr12} {period}"
    return f"{_fmt(h)} \u2013 {_fmt((h + 1) % 24)}"

"""Sales analytics: daily KPIs, top products, peak ordering hours.

All queries use SQLAlchemy aggregation where possible.

Definitions used consistently:
  Revenue       \u2014 SUM(payable_paise) of PAID+ orders
  Paid+         \u2014 status IN ('PAID','PREPARING','READY','OUT_FOR_DELIVERY','COMPLETED')
  Pending       \u2014 status = 'AWAITING_PAYMENT'
  Exception     \u2014 payment_state = 'NEEDS_OWNER'
  Today         \u2014 IST calendar day (created_at converted to IST)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shopbot.clock import IST
from shopbot.models import Credit, Order, OrderItem
from shopbot.money import format_inr

# Statuses that indicate an order was fulfilled / paid
PAID_STATUSES = ("PAID", "PREPARING", "READY", "OUT_FOR_DELIVERY", "COMPLETED")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class DailySalesKPI:
    date_label: str
    total_orders: int
    paid_orders: int
    revenue_paise: int
    revenue_display: str
    aov_paise: int
    aov_display: str
    pending_orders: int
    payment_exceptions: int
    unmatched_credits: int


@dataclass
class TopProduct:
    rank: int
    name: str
    qty_sold: int
    revenue_paise: int
    revenue_display: str
    order_count: int  # orders that contained this item


@dataclass
class PeakHour:
    hour_label: str   # e.g. "8 PM \u2013 9 PM"
    hour_ist: int     # 0\u201323
    order_count: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ist_day_bounds(for_date: date) -> tuple[datetime, datetime]:
    """Return UTC datetimes for the start and end of an IST calendar day."""
    import datetime as _dt

    start_ist = _dt.datetime(for_date.year, for_date.month, for_date.day, 0, 0, 0, tzinfo=IST)
    end_ist = start_ist + timedelta(days=1)
    return start_ist.astimezone(_dt.timezone.utc), end_ist.astimezone(_dt.timezone.utc)


def _today_ist() -> date:
    return datetime.now(IST).date()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def calculate_daily_sales(
    session: Session,
    for_date: date | None = None,
) -> DailySalesKPI:
    """Calculate the main business KPIs for a given IST calendar day."""
    if for_date is None:
        for_date = _today_ist()

    day_start_utc, day_end_utc = _ist_day_bounds(for_date)
    date_label = for_date.strftime("%-d %B %Y") if hasattr(for_date, "strftime") else str(for_date)

    # All orders created on this IST day
    day_orders = session.scalars(
        select(Order).where(
            Order.created_at >= day_start_utc,
            Order.created_at < day_end_utc,
        )
    ).all()

    paid = [o for o in day_orders if o.status in PAID_STATUSES]
    pending = [o for o in day_orders if o.status == "AWAITING_PAYMENT"]
    exceptions = [o for o in day_orders if o.payment_state == "NEEDS_OWNER"]

    revenue = sum(o.payable_paise for o in paid)
    aov = revenue // len(paid) if paid else 0

    unmatched_credits = session.scalar(
        select(func.count(Credit.id)).where(
            Credit.status == "UNMATCHED",
            Credit.received_at >= day_start_utc,
            Credit.received_at < day_end_utc,
        )
    ) or 0

    return DailySalesKPI(
        date_label=date_label,
        total_orders=len(day_orders),
        paid_orders=len(paid),
        revenue_paise=revenue,
        revenue_display=format_inr(revenue),
        aov_paise=aov,
        aov_display=format_inr(aov),
        pending_orders=len(pending),
        payment_exceptions=len(exceptions),
        unmatched_credits=unmatched_credits,
    )


def get_top_products(
    session: Session,
    for_date: date | None = None,
    days: int = 1,
    limit: int = 10,
) -> list[TopProduct]:
    """Return the top-selling items by quantity sold.

    Args:
        for_date: end date (inclusive, IST). Defaults to today.
        days: number of days to include (1 = today only, 7 = last week, etc.)
        limit: maximum items to return.
    """
    if for_date is None:
        for_date = _today_ist()

    end_date = for_date
    start_date = for_date - timedelta(days=days - 1)
    start_utc, _ = _ist_day_bounds(start_date)
    _, end_utc = _ist_day_bounds(end_date)

    # Paid order IDs in window
    paid_order_ids = session.scalars(
        select(Order.id).where(
            Order.status.in_(PAID_STATUSES),
            Order.created_at >= start_utc,
            Order.created_at < end_utc,
        )
    ).all()

    if not paid_order_ids:
        return []

    # Aggregate by item name (use name_snapshot so renamed items are correct)
    rows: list[Any] = session.execute(
        select(
            OrderItem.name_snapshot,
            func.sum(OrderItem.qty).label("total_qty"),
            func.sum(OrderItem.line_total_paise).label("total_revenue"),
            func.count(OrderItem.order_id.distinct()).label("order_count"),
        )
        .where(OrderItem.order_id.in_(paid_order_ids))
        .group_by(OrderItem.name_snapshot)
        .order_by(func.sum(OrderItem.qty).desc())
        .limit(limit)
    ).all()

    return [
        TopProduct(
            rank=i + 1,
            name=row.name_snapshot,
            qty_sold=row.total_qty,
            revenue_paise=row.total_revenue,
            revenue_display=format_inr(row.total_revenue),
            order_count=row.order_count,
        )
        for i, row in enumerate(rows)
    ]


def get_peak_hours(
    session: Session,
    for_date: date | None = None,
    days: int = 1,
    top_n: int = 5,
) -> list[PeakHour]:
    """Return the busiest ordering hours (IST) sorted by order count."""
    if for_date is None:
        for_date = _today_ist()

    end_date = for_date
    start_date = for_date - timedelta(days=days - 1)
    start_utc, _ = _ist_day_bounds(start_date)
    _, end_utc = _ist_day_bounds(end_date)

    orders = session.scalars(
        select(Order).where(
            Order.created_at >= start_utc,
            Order.created_at < end_utc,
        )
    ).all()

    if not orders:
        return []

    from collections import Counter

    hour_counts: Counter[int] = Counter()
    for o in orders:
        if o.created_at:
            ist_dt = o.created_at.astimezone(IST)
            hour_counts[ist_dt.hour] += 1

    def _hour_label(h: int) -> str:
        def _fmt(hr: int) -> str:
            period = "AM" if hr < 12 else "PM"
            hr12 = hr % 12 or 12
            return f"{hr12} {period}"
        return f"{_fmt(h)} \u2013 {_fmt((h + 1) % 24)}"

    result = [
        PeakHour(hour_label=_hour_label(h), hour_ist=h, order_count=cnt)
        for h, cnt in hour_counts.most_common(top_n)
    ]
    return result

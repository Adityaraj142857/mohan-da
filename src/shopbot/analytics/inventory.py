"""Inventory analytics: stock levels, restock recommendations, demand estimation.

Uses the Inventory table (new) plus historical OrderItem data for demand estimation.
If no inventory records exist, all functions return graceful empty results.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shopbot.analytics.constants import (
    DEMAND_RECENT_DAYS,
    LOW_DAYS_OF_STOCK_THRESHOLD,
    MIN_DEMAND_HISTORY_DAYS,
)
from shopbot.clock import IST
from shopbot.models import Inventory, Order, OrderItem

PAID_STATUSES = ("PAID", "PREPARING", "READY", "OUT_FOR_DELIVERY", "COMPLETED")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class InventoryStatus:
    inventory_id: str
    item_name: str
    current_stock: int
    low_stock_threshold: int
    target_stock: int
    estimated_daily_demand: float | None    # None if insufficient history
    days_of_stock: float | None             # current_stock / daily_demand
    status: str                             # "LOW" | "CRITICAL" | "OK"
    recommended_restock: int                # max(0, target - current)
    restock_reason: str


@dataclass
class InventorySummary:
    items: list[InventoryStatus]
    low_stock_alerts: list[InventoryStatus]
    total_items_tracked: int


# ---------------------------------------------------------------------------
# Demand estimation (simple moving average)
# ---------------------------------------------------------------------------


def _estimate_daily_demand(session: Session, item_name: str) -> float | None:
    """Estimate daily demand using a weighted average:
      70% weight on the recent DEMAND_RECENT_DAYS average,
      30% weight on the historical (30-day) average.

    Returns None if fewer than MIN_DEMAND_HISTORY_DAYS of data exist.
    """
    today = datetime.now(IST).date()
    history_start = today - timedelta(days=30)
    recent_start = today - timedelta(days=DEMAND_RECENT_DAYS)

    # Convert to UTC
    def _utc_start(d: date) -> datetime:
        from shopbot.analytics.sales import _ist_day_bounds
        return _ist_day_bounds(d)[0]

    hist_start_utc = _utc_start(history_start)
    recent_start_utc = _utc_start(recent_start)
    today_end_utc = _utc_start(today + timedelta(days=1))

    # Paid orders in last 30 days
    paid_ids_30 = session.scalars(
        select(Order.id).where(
            Order.status.in_(PAID_STATUSES),
            Order.created_at >= hist_start_utc,
            Order.created_at < today_end_utc,
        )
    ).all()

    if not paid_ids_30:
        return None

    # Days with any data
    order_dates = session.execute(
        select(Order.created_at).where(Order.id.in_(paid_ids_30))
    ).scalars().all()

    unique_days = {dt.astimezone(IST).date() for dt in order_dates if dt}
    if len(unique_days) < MIN_DEMAND_HISTORY_DAYS:
        return None

    def _qty_in_window(order_ids: list[str]) -> int:
        if not order_ids:
            return 0
        result = session.scalar(
            select(func.sum(OrderItem.qty)).where(
                OrderItem.order_id.in_(order_ids),
                OrderItem.name_snapshot == item_name,
            )
        )
        return result or 0

    # 30-day historical
    hist_qty = _qty_in_window(list(paid_ids_30))
    hist_days = max(1, len({dt.astimezone(IST).date() for dt in order_dates if dt}))
    hist_avg = hist_qty / hist_days

    # Recent window
    paid_ids_recent = [
        oid for oid, dt in zip(paid_ids_30, order_dates)
        if dt and dt >= recent_start_utc
    ]
    recent_qty = _qty_in_window(paid_ids_recent)
    recent_avg = recent_qty / DEMAND_RECENT_DAYS

    # Weighted average
    weighted = 0.3 * hist_avg + 0.7 * recent_avg
    return round(weighted, 2)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_inventory_status(session: Session) -> InventorySummary:
    """Return current stock status for all tracked inventory items."""
    all_inv = session.scalars(select(Inventory)).all()

    statuses: list[InventoryStatus] = []
    for inv in all_inv:
        demand = _estimate_daily_demand(session, inv.item_name)

        if demand and demand > 0:
            days_of_stock = round(inv.current_stock / demand, 1)
        else:
            days_of_stock = None

        # Status
        if inv.current_stock <= inv.reorder_level:
            status = "CRITICAL"
        elif inv.current_stock <= inv.low_stock_threshold:
            status = "LOW"
        else:
            status = "OK"

        # Override with days-of-stock check
        if days_of_stock is not None and days_of_stock < LOW_DAYS_OF_STOCK_THRESHOLD:
            if status == "OK":
                status = "LOW"

        restock = max(0, inv.target_stock - inv.current_stock)

        if restock == 0:
            reason = "Stock level adequate."
        elif demand is not None:
            reason = (
                f"Current stock ({inv.current_stock}) covers "
                f"~{days_of_stock} days at {demand}/day demand. "
                f"Restock {restock} to reach target of {inv.target_stock}."
            )
        else:
            reason = (
                f"Stock is below target ({inv.target_stock}). "
                f"Insufficient history for demand estimate."
            )

        statuses.append(InventoryStatus(
            inventory_id=inv.id,
            item_name=inv.item_name,
            current_stock=inv.current_stock,
            low_stock_threshold=inv.low_stock_threshold,
            target_stock=inv.target_stock,
            estimated_daily_demand=demand,
            days_of_stock=days_of_stock,
            status=status,
            recommended_restock=restock,
            restock_reason=reason,
        ))

    # Sort: CRITICAL first, then LOW, then OK
    order_map = {"CRITICAL": 0, "LOW": 1, "OK": 2}
    statuses.sort(key=lambda s: (order_map.get(s.status, 9), -s.recommended_restock))
    low_alerts = [s for s in statuses if s.status in ("LOW", "CRITICAL")]

    return InventorySummary(
        items=statuses,
        low_stock_alerts=low_alerts,
        total_items_tracked=len(statuses),
    )


def update_stock(session: Session, inventory_id: str, new_quantity: int) -> bool:
    """Manually update stock level. Returns True if found and updated."""
    inv = session.get(Inventory, inventory_id)
    if inv is None:
        return False
    inv.current_stock = max(0, new_quantity)
    inv.updated_at = datetime.now(IST)
    return True

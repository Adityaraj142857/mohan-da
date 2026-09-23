"""Daily business summary (deterministic text template).

Assembles already-calculated facts into a structured owner report.
No LLM dependency — business logic is entirely in the analytics services.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from shopbot.analytics.inventory import get_inventory_status
from shopbot.analytics.products import get_cross_sell_pairs
from shopbot.analytics.recommendations import get_offer_recommendations
from shopbot.analytics.sales import (
    calculate_daily_sales,
    get_peak_hours,
    get_top_products,
)
from shopbot.clock import IST
from datetime import datetime


@dataclass
class DailySummary:
    date_label: str
    kpi: Any                 # DailySalesKPI
    top_products: list[Any]  # list[TopProduct]
    peak_hours: list[Any]    # list[PeakHour]
    inventory: Any           # InventorySummary
    cross_sell: Any          # ProductCrossellSummary
    recommendations: Any     # RecommendationSummary
    text_report: str         # formatted plain-text report


def generate_daily_summary(session: Session, for_date: date | None = None) -> DailySummary:
    """Generate the complete daily business summary."""
    if for_date is None:
        for_date = datetime.now(IST).date()

    kpi = calculate_daily_sales(session, for_date=for_date)
    top_products = get_top_products(session, for_date=for_date, days=1, limit=5)
    top_7d = get_top_products(session, for_date=for_date, days=7, limit=5)
    peak_hours = get_peak_hours(session, for_date=for_date, days=1, top_n=3)
    inventory = get_inventory_status(session)
    cross_sell = get_cross_sell_pairs(session, limit=5)
    recommendations = get_offer_recommendations(session)

    report = _format_report(
        kpi=kpi,
        top_products=top_products,
        top_7d=top_7d,
        peak_hours=peak_hours,
        inventory=inventory,
        cross_sell=cross_sell,
        recommendations=recommendations,
    )

    return DailySummary(
        date_label=kpi.date_label,
        kpi=kpi,
        top_products=top_products,
        peak_hours=peak_hours,
        inventory=inventory,
        cross_sell=cross_sell,
        recommendations=recommendations,
        text_report=report,
    )


def _format_report(*, kpi, top_products, top_7d, peak_hours, inventory, cross_sell, recommendations) -> str:
    sep = "-" * 47
    lines = [
        sep,
        "  MOHANDA DAILY BUSINESS REPORT",
        f"  {kpi.date_label}",
        sep,
        "",
        "TODAY'S BUSINESS",
        f"  Orders (created today) : {kpi.total_orders}",
        f"  Paid orders            : {kpi.paid_orders}",
        f"  Revenue                : {kpi.revenue_display}",
        f"  Average Order Value    : {kpi.aov_display}",
        f"  Pending payment        : {kpi.pending_orders}",
        f"  Payment exceptions     : {kpi.payment_exceptions}",
        f"  Unmatched credits      : {kpi.unmatched_credits}",
    ]

    lines += ["", "TOP-SELLING ITEMS (TODAY)"]
    if top_products:
        for p in top_products:
            lines.append(f"  {p.rank}. {p.name:<20} {p.qty_sold} sold  {p.revenue_display}")
    else:
        lines.append("  No sales recorded today.")

    lines += ["", "TOP-SELLING ITEMS (LAST 7 DAYS)"]
    if top_7d:
        for p in top_7d:
            lines.append(f"  {p.rank}. {p.name:<20} {p.qty_sold} sold")
    else:
        lines.append("  Insufficient 7-day data.")

    lines += ["", "PEAK SALES HOURS (TODAY)"]
    if peak_hours:
        for ph in peak_hours:
            bar = "\u2588" * min(ph.order_count, 20)
            lines.append(f"  {ph.hour_label:<18} {ph.order_count:>3} orders  {bar}")
    else:
        lines.append("  No orders today.")

    lines += ["", "INVENTORY ALERTS"]
    if inventory.low_stock_alerts:
        for item in inventory.low_stock_alerts:
            icon = "\u26a0\ufe0f" if item.status == "LOW" else "\U0001f6a8"
            dem = f"~{item.estimated_daily_demand}/day" if item.estimated_daily_demand else "demand unknown"
            lines.append(f"  {icon} {item.item_name}: {item.current_stock} units  ({dem})")
    elif inventory.total_items_tracked == 0:
        lines.append("  Inventory not configured.")
    else:
        lines.append("  All items adequately stocked.")

    lines += ["", "RESTOCK RECOMMENDATIONS"]
    restock_items = [s for s in inventory.items if s.recommended_restock > 0]
    if restock_items:
        for item in restock_items[:5]:
            lines.append(f"  {item.item_name}: restock ~{item.recommended_restock} units")
    else:
        lines.append("  No restocking needed.")

    lines += ["", "CROSS-SELL OPPORTUNITIES"]
    if cross_sell.insufficient_data:
        lines.append(f"  {cross_sell.message}")
    else:
        for pair in cross_sell.pairs[:3]:
            lines.append(f"  {pair.source_item} \u2192 {pair.target_item}  ({pair.confidence_pct} confidence)")

    lines += ["", "OFFER RECOMMENDATIONS"]
    if recommendations.offer_recommendations:
        for rec in recommendations.offer_recommendations[:3]:
            lines.append(f"  [{rec.confidence_label}] {rec.title}")
            lines.append(f"    {rec.reason}")
    else:
        lines.append("  No offer recommendations today.")

    lines += [
        "",
        sep,
        "  System: MohanDa ShopBot Business Analytics",
        "  All values are from actual order data.",
        sep,
    ]

    return "\n".join(lines)

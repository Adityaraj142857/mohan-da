"""Cross-sell / association analysis using historical paid order data.

Uses item co-occurrence (market-basket style) to calculate:
  - pair counts
  - support (fraction of all paid orders containing both items)
  - confidence (fraction of source-item orders that also contain target item)

No ML model. Pure frequency counting from the existing OrderItem table.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from shopbot.analytics.constants import (
    MIN_CROSSSELL_CONFIDENCE,
    MIN_CROSSSELL_PAIR_COUNT,
    MIN_ORDERS_FOR_CROSSSELL,
)
from shopbot.models import Order, OrderItem

PAID_STATUSES = ("PAID", "PREPARING", "READY", "OUT_FOR_DELIVERY", "COMPLETED")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CrossSellPair:
    source_item: str
    target_item: str
    pair_count: int           # orders containing both
    source_count: int         # orders containing source
    confidence: float         # pair_count / source_count
    confidence_pct: str       # e.g. "42%"
    support: float            # pair_count / total_paid_orders
    explanation: str          # human-readable reason


@dataclass
class ProductCrossellSummary:
    """Top cross-sell pairs for the owner dashboard."""
    pairs: list[CrossSellPair]
    total_paid_orders: int
    insufficient_data: bool
    message: str


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------


def get_cross_sell_pairs(
    session: Session,
    limit: int = 10,
) -> ProductCrossellSummary:
    """Calculate cross-sell associations from all paid order history."""
    paid_order_ids = session.scalars(
        select(Order.id).where(Order.status.in_(PAID_STATUSES))
    ).all()
    total_paid = len(paid_order_ids)

    if total_paid < MIN_ORDERS_FOR_CROSSSELL:
        return ProductCrossellSummary(
            pairs=[],
            total_paid_orders=total_paid,
            insufficient_data=True,
            message=f"Need at least {MIN_ORDERS_FOR_CROSSSELL} paid orders for reliable "
                    f"cross-sell analysis (currently {total_paid}).",
        )

    # Build order \u2192 item-names mapping
    order_items: dict[str, set[str]] = defaultdict(set)
    rows = session.execute(
        select(OrderItem.order_id, OrderItem.name_snapshot).where(
            OrderItem.order_id.in_(paid_order_ids)
        )
    ).all()
    for order_id, name in rows:
        order_items[order_id].add(name)

    # Count per-item occurrence
    item_counts: Counter[str] = Counter()
    for items in order_items.values():
        for item in items:
            item_counts[item] += 1

    # Count pair co-occurrence
    pair_counts: Counter[tuple[str, str]] = Counter()
    for items in order_items.values():
        sorted_items = sorted(items)
        for i in range(len(sorted_items)):
            for j in range(i + 1, len(sorted_items)):
                pair_counts[(sorted_items[i], sorted_items[j])] += 1

    # Build cross-sell pairs (directional: A\u2192B and B\u2192A)
    results: list[CrossSellPair] = []
    for (a, b), count in pair_counts.most_common():
        if count < MIN_CROSSSELL_PAIR_COUNT:
            continue
        for source, target in [(a, b), (b, a)]:
            src_count = item_counts[source]
            if src_count < MIN_ORDERS_FOR_CROSSSELL:
                continue
            confidence = count / src_count
            if confidence < MIN_CROSSSELL_CONFIDENCE:
                continue
            results.append(CrossSellPair(
                source_item=source,
                target_item=target,
                pair_count=count,
                source_count=src_count,
                confidence=round(confidence, 3),
                confidence_pct=f"{round(confidence * 100)}%",
                support=round(count / total_paid, 3),
                explanation=f"{round(confidence * 100)}% of {source!r} orders also contain {target!r}",
            ))

    # Sort by confidence desc, then pair count desc; deduplicate source\u2192target
    results.sort(key=lambda p: (-p.confidence, -p.pair_count))
    seen: set[tuple[str, str]] = set()
    deduped: list[CrossSellPair] = []
    for p in results:
        key = (p.source_item, p.target_item)
        if key not in seen:
            seen.add(key)
            deduped.append(p)
        if len(deduped) >= limit:
            break

    if not deduped:
        return ProductCrossellSummary(
            pairs=[],
            total_paid_orders=total_paid,
            insufficient_data=True,
            message="Not enough order history for reliable cross-sell recommendations.",
        )

    return ProductCrossellSummary(
        pairs=deduped,
        total_paid_orders=total_paid,
        insufficient_data=False,
        message=f"Based on {total_paid} paid orders.",
    )


def get_recommendations_for_order(
    session: Session,
    current_item_names: list[str],
    limit: int = 2,
) -> list[CrossSellPair]:
    """Given a customer's current order items, suggest items to add.

    Filters out items already in the order.
    Returns an empty list if insufficient data.
    """
    summary = get_cross_sell_pairs(session, limit=50)
    if summary.insufficient_data:
        return []

    current = {n.lower() for n in current_item_names}
    recs: list[CrossSellPair] = []
    for pair in summary.pairs:
        if pair.source_item.lower() in current and pair.target_item.lower() not in current:
            recs.append(pair)
        if len(recs) >= limit:
            break
    return recs

"""Offer and promotion recommendations.

Deterministic rules combining:
  - sales velocity (recent vs. historical)
  - inventory levels
  - cross-sell pair strength

The system RECOMMENDS offers to the owner. The owner APPROVES them.
Recommendations never automatically change any price or order.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shopbot.analytics.constants import (
    MIN_CROSSSELL_CONFIDENCE,
    MIN_DEMAND_HISTORY_DAYS,
    PROMO_MIN_HISTORICAL_DAILY,
    PROMO_VELOCITY_DROP_THRESHOLD,
)
from shopbot.analytics.inventory import get_inventory_status
from shopbot.analytics.products import get_cross_sell_pairs
from shopbot.clock import IST
from shopbot.models import Order, OrderItem, Promotion
from shopbot.money import format_inr

PAID_STATUSES = ("PAID", "PREPARING", "READY", "OUT_FOR_DELIVERY", "COMPLETED")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class OfferRecommendation:
    """A generated offer recommendation awaiting owner approval."""
    rec_type: str         # "velocity_drop" | "cross_sell_bundle" | "low_stock_push"
    title: str
    description: str
    reason: str
    evidence: str
    suggested_discount_paise: int
    item_names: list[str]
    confidence_label: str  # "Strong" | "Moderate" | "Weak"


@dataclass
class OwnerPromotion:
    """An existing Promotion record ready for display."""
    promotion_id: str
    name: str
    offer_type: str
    item_names: list[str]
    discount_paise: int
    discount_display: str
    description: str | None
    reason: str | None
    active: bool
    owner_approved: bool
    created_display: str


@dataclass
class RecommendationSummary:
    offer_recommendations: list[OfferRecommendation]
    cross_sell_pairs: list  # CrossSellPair list
    pending_promotions: list[OwnerPromotion]
    active_promotions: list[OwnerPromotion]
    insufficient_data: bool
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _daily_avg(session: Session, item_name: str, start_days_ago: int, end_days_ago: int = 0) -> float:
    """Average daily quantity sold for an item between two IST day offsets."""
    from shopbot.analytics.sales import _ist_day_bounds

    today = datetime.now(IST).date()
    start = today - timedelta(days=start_days_ago)
    end = today - timedelta(days=end_days_ago)

    start_utc = _ist_day_bounds(start)[0]
    end_utc = _ist_day_bounds(end + timedelta(days=1))[0]
    window_days = max(1, start_days_ago - end_days_ago)

    paid_ids = session.scalars(
        select(Order.id).where(
            Order.status.in_(PAID_STATUSES),
            Order.created_at >= start_utc,
            Order.created_at < end_utc,
        )
    ).all()

    if not paid_ids:
        return 0.0

    qty = session.scalar(
        select(func.sum(OrderItem.qty)).where(
            OrderItem.order_id.in_(paid_ids),
            OrderItem.name_snapshot == item_name,
        )
    ) or 0

    return qty / window_days


# ---------------------------------------------------------------------------
# Recommendation generators
# ---------------------------------------------------------------------------


def _velocity_drop_recommendations(session: Session) -> list[OfferRecommendation]:
    """Items whose recent (3-day) sales are significantly below 30-day average."""
    # Get distinct item names from recent paid orders
    thirty_ago = datetime.now(IST) - timedelta(days=30)
    paid_ids = session.scalars(
        select(Order.id).where(
            Order.status.in_(PAID_STATUSES),
            Order.created_at >= thirty_ago.astimezone(datetime.now(IST).tzinfo),
        )
    ).all()

    items_names = session.execute(
        select(OrderItem.name_snapshot.distinct()).where(
            OrderItem.order_id.in_(paid_ids)
        )
    ).scalars().all() if paid_ids else []

    recs: list[OfferRecommendation] = []
    for name in items_names:
        hist_avg = _daily_avg(session, name, start_days_ago=30, end_days_ago=3)
        recent_avg = _daily_avg(session, name, start_days_ago=3, end_days_ago=0)

        if hist_avg < PROMO_MIN_HISTORICAL_DAILY:
            continue  # too rarely sold historically to recommend promo

        if hist_avg == 0:
            continue

        ratio = recent_avg / hist_avg
        if ratio < PROMO_VELOCITY_DROP_THRESHOLD:
            drop_pct = round((1 - ratio) * 100)
            recs.append(OfferRecommendation(
                rec_type="velocity_drop",
                title=f"Consider a {name} promotion",
                description=(
                    f"{name} sales have dropped {drop_pct}% over the last 3 days "
                    f"compared to the 30-day average."
                ),
                reason=f"Recent sales: {recent_avg:.1f}/day vs historical: {hist_avg:.1f}/day",
                evidence=f"{drop_pct}% sales decline detected",
                suggested_discount_paise=500,  # ₹5 default suggestion
                item_names=[name],
                confidence_label="Strong" if ratio < 0.4 else "Moderate",
            ))

    return recs[:3]


def _cross_sell_bundle_recommendations(session: Session) -> list[OfferRecommendation]:
    """Suggest bundle offers for the top cross-sell pairs."""
    summary = get_cross_sell_pairs(session, limit=5)
    if summary.insufficient_data:
        return []

    recs: list[OfferRecommendation] = []
    seen: set[frozenset[str]] = set()

    for pair in summary.pairs:
        key = frozenset([pair.source_item, pair.target_item])
        if key in seen:
            continue
        seen.add(key)

        if pair.confidence < MIN_CROSSSELL_CONFIDENCE + 0.05:
            continue

        recs.append(OfferRecommendation(
            rec_type="cross_sell_bundle",
            title=f"{pair.source_item} + {pair.target_item} bundle",
            description=(
                f"{pair.confidence_pct} of {pair.source_item!r} orders also contain "
                f"{pair.target_item!r}. A combo offer may increase basket size."
            ),
            reason=f"Co-occurrence in {pair.pair_count} paid orders (confidence: {pair.confidence_pct})",
            evidence=f"Based on {pair.source_count} orders containing {pair.source_item!r}",
            suggested_discount_paise=500,
            item_names=[pair.source_item, pair.target_item],
            confidence_label="Strong" if pair.confidence >= 0.4 else "Moderate",
        ))

    return recs[:3]


def get_offer_recommendations(session: Session) -> RecommendationSummary:
    """Generate all offer recommendations for the owner dashboard."""
    velocity_recs = _velocity_drop_recommendations(session)
    bundle_recs = _cross_sell_bundle_recommendations(session)
    all_recs = velocity_recs + bundle_recs

    # Fetch existing promotions
    promotions = session.scalars(select(Promotion).order_by(Promotion.created_at.desc())).all()
    pending = [p for p in promotions if not p.owner_approved]
    active = [p for p in promotions if p.owner_approved and p.active]

    def _promo_row(p: Promotion) -> OwnerPromotion:
        return OwnerPromotion(
            promotion_id=p.id,
            name=p.name,
            offer_type=p.offer_type,
            item_names=p.item_names or [],
            discount_paise=p.discount_paise,
            discount_display=format_inr(p.discount_paise),
            description=p.description,
            reason=p.reason,
            active=p.active,
            owner_approved=p.owner_approved,
            created_display=p.created_at.astimezone(IST).strftime("%-d %b %Y, %I:%M %p")
            if p.created_at else "",
        )

    cross_sell = get_cross_sell_pairs(session)
    insufficient = not all_recs and cross_sell.insufficient_data
    msg = cross_sell.message if cross_sell.insufficient_data else f"{len(all_recs)} offer recommendation(s) generated."

    return RecommendationSummary(
        offer_recommendations=all_recs,
        cross_sell_pairs=cross_sell.pairs,
        pending_promotions=[_promo_row(p) for p in pending],
        active_promotions=[_promo_row(p) for p in active],
        insufficient_data=insufficient,
        message=msg,
    )


def create_promotion_from_recommendation(
    session: Session,
    rec: OfferRecommendation,
) -> Promotion:
    """Persist a Promotion record (unapproved) from a recommendation."""
    promo = Promotion(
        name=rec.title,
        offer_type="fixed",
        item_ids=[],
        item_names=rec.item_names,
        discount_paise=rec.suggested_discount_paise,
        description=rec.description,
        reason=rec.reason,
        active=False,
        owner_approved=False,
    )
    session.add(promo)
    session.flush()
    return promo

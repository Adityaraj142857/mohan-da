"""Configurable thresholds for analytics and segmentation.

All values are intentionally in one place so the owner can tune them
without hunting through business logic.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Customer segmentation thresholds
# ---------------------------------------------------------------------------

#: Minimum paid orders before a customer is assigned any segment.
#: Below this, the customer is labelled "New Customer".
MIN_ORDERS_FOR_SEGMENT: int = 3

#: Minimum paid orders before personalised recommendations are shown.
MIN_ORDERS_FOR_PERSONALIZATION: int = 3

#: Orders per week (rolling 30-day average) to qualify as "Frequent Buyer".
FREQUENT_ORDERS_PER_WEEK: float = 2.0

#: Average order value (paise) to qualify as "High-Value Customer".
HIGH_VALUE_AOV_PAISE: int = 20_000  # \u20b9200

#: Days since last order to classify a customer as "Dormant".
DORMANT_DAYS: int = 14

# ---------------------------------------------------------------------------
# Cross-sell / association analysis thresholds
# ---------------------------------------------------------------------------

#: The source item must appear in at least this many paid orders before
#: cross-sell recommendations are generated.
MIN_ORDERS_FOR_CROSSSELL: int = 5

#: A pair (A, B) must co-occur in at least this many orders.
MIN_CROSSSELL_PAIR_COUNT: int = 3

#: Minimum confidence (0\u20131.0) to surface a cross-sell recommendation.
MIN_CROSSSELL_CONFIDENCE: float = 0.20

# ---------------------------------------------------------------------------
# Demand estimation thresholds
# ---------------------------------------------------------------------------

#: Minimum days of order history required before we produce a demand estimate.
MIN_DEMAND_HISTORY_DAYS: int = 7

#: Number of recent days used for the "recent" average in demand estimation.
DEMAND_RECENT_DAYS: int = 3

# ---------------------------------------------------------------------------
# Inventory / offer thresholds
# ---------------------------------------------------------------------------

#: If (current_stock / estimated_daily_demand) < this, raise a restock alert.
LOW_DAYS_OF_STOCK_THRESHOLD: float = 1.5

#: Sales velocity drop required to recommend a promotional offer.
#: If recent_avg < PROMO_VELOCITY_DROP_THRESHOLD * historical_avg, suggest promo.
PROMO_VELOCITY_DROP_THRESHOLD: float = 0.60

#: Minimum historical daily sales to consider an item for promotion.
PROMO_MIN_HISTORICAL_DAILY: float = 2.0

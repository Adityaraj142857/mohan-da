"""Analytics service package for MohanDa Business Operations Platform.

All modules in this package are READ-ONLY with respect to payment state.
They query existing Order/OrderItem/Customer/Credit data plus the new
Inventory and Promotion tables.

Architecture:
  sales.py          \u2014 daily KPIs, top products, peak hours
  customers.py      \u2014 customer profiles, segments
  products.py       \u2014 cross-sell / association analysis
  inventory.py      \u2014 stock levels, restock recommendations
  recommendations.py \u2014 offer / cross-sell recommendations for the owner
  daily_summary.py  \u2014 deterministic daily business report
"""

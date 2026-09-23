import pytest
from datetime import timedelta
from shopbot.analytics.sales import calculate_daily_sales, get_top_products, get_peak_hours
from shopbot.harness import Harness
from shopbot.clock import IST

def test_calculate_daily_sales_empty():
    h = Harness()
    with h.db.session() as session:
        kpi = calculate_daily_sales(session, for_date=h.clock.now().astimezone(IST).date())
        assert kpi.total_orders == 0
        assert kpi.revenue_paise == 0

def test_sales_kpis():
    h = Harness()
    # Create a paid order
    h.confirm_order("wa1", "1 maggi", "takeout")
    order = h.get_active_order("wa1")
    h.owner_approve(order.code)

    # Create a pending order
    h.confirm_order("wa2", "1 coke", "takeout")

    with h.db.session() as session:
        kpi = calculate_daily_sales(session, for_date=h.clock.now().astimezone(IST).date())
        assert kpi.total_orders == 2
        assert kpi.paid_orders == 1
        assert kpi.pending_orders == 1
        assert kpi.revenue_paise > 0

def test_top_products():
    h = Harness()
    h.confirm_order("wa1", "2 maggi", "takeout")
    order = h.get_active_order("wa1")
    h.owner_approve(order.code)

    h.confirm_order("wa2", "1 maggi, 1 coke", "takeout")
    order2 = h.get_active_order("wa2")
    h.owner_approve(order2.code)

    with h.db.session() as session:
        top = get_top_products(session, for_date=h.clock.now().astimezone(IST).date())
        assert len(top) == 2
        assert top[0].name == "Maggi"
        assert top[0].qty_sold == 3
        assert top[1].name == "Cold Drink"
        assert top[1].qty_sold == 1

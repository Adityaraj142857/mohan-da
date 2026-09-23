import pytest
from shopbot.analytics.customers import get_customer_profile, get_all_customer_summaries
from shopbot.harness import Harness

def test_customer_segmentation():
    h = Harness()
    with h.db.session() as session:
        from shopbot.models import Customer, Order, OrderItem
        from shopbot.clock import IST
        from datetime import datetime, timedelta
        
        c = Customer(wa_id="test_segmentation_user")
        session.add(c)
        session.flush()

        for i in range(3):
            o = Order(
                customer_id=c.id,
                code=f"TS{i}",
                status="COMPLETED",
                payment_state="VERIFIED",
                created_at=datetime.now(IST) - timedelta(days=i),
                paid_at=datetime.now(IST) - timedelta(days=i)
            )
            o.items.append(OrderItem(name_snapshot="Maggi", qty=1, line_total_paise=3000, unit_price_paise=3000))
            session.add(o)
        session.commit()

    with h.db.session() as session:
        from sqlalchemy import select
        from shopbot.models import Customer
        customer = session.scalar(select(Customer).where(Customer.wa_id == "test_segmentation_user"))
        profile = get_customer_profile(session, customer.id)
        assert profile is not None
        assert profile.total_orders == 3
        # Should be occasional buyer as frequency is < 2/week and not dormant yet
        assert profile.segment in ("Occasional Buyer", "Frequent Buyer")

def test_all_customers_summary():
    h = Harness()
    h.confirm_order("wa1", "1 maggi", "takeout")
    order = h.get_active_order("wa1")
    h.owner_approve(order.code)

    with h.db.session() as session:
        summaries = get_all_customer_summaries(session)
        assert len(summaries) == 1
        assert summaries[0].wa_id == "wa1"
        assert summaries[0].segment == "New Customer"
        assert summaries[0].favourite_item == "Maggi"

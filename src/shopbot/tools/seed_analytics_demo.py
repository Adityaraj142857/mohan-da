"""Seeds the database with deterministic analytics data for demo purposes.

Creates:
- 5 unique customers with 3-20 orders each
- Realistic time distribution over the last 7 days
- Association patterns (Maggi+Coke frequently bought together)
- Inventory levels for alerts
- One pending promotion
"""

from __future__ import annotations

import random
from datetime import timedelta

from sqlalchemy.orm import Session

from shopbot.clock import IST
from shopbot.config import Settings
from shopbot.db import Database
from shopbot.models import (
    Credit,
    Customer,
    EventLog,
    Inventory,
    Order,
    OrderItem,
    Promotion,
    Screenshot,
)
from shopbot.money import rupees_to_paise


def seed_analytics_demo(db: Database, settings: Settings) -> None:
    from shopbot.menu.loader import load_menu_yaml
    from shopbot.config import REPO_ROOT
    from datetime import datetime
    import json

    with db.session() as session:
        # 1. Setup minimal menu items if not exists
        menu_items = {
            "Maggi": rupees_to_paise(30),
            "Coke": rupees_to_paise(20),
            "Chips": rupees_to_paise(15),
            "Coffee": rupees_to_paise(15),
            "Sandwich": rupees_to_paise(40),
            "Pasta": rupees_to_paise(60),
            "Milkshake": rupees_to_paise(45),
            "Ice Tea": rupees_to_paise(40),
            "Chicken Strips": rupees_to_paise(60),
        }

        # Clear existing non-essential data for a clean demo (child tables first)
        session.query(OrderItem).delete()
        session.query(Credit).delete()
        session.query(Screenshot).delete()
        session.query(EventLog).delete()
        session.query(Order).delete()
        session.query(Customer).delete()
        session.query(Inventory).delete()
        session.query(Promotion).delete()
        session.commit()

        print("Seeding analytics demo data...")

        # 2. Customers
        customers = [
            Customer(wa_id="919999900001", name="Rahul"),
            Customer(wa_id="919999900002", name="Priya"),
            Customer(wa_id="919999900003", name="Amit (Frequent)"),
            Customer(wa_id="919999900004", name="Neha (New)"),
            Customer(wa_id="919999900005", name="Vikram (Dormant)"),
        ]
        for c in customers:
            session.add(c)
        session.flush()

        # 3. Deterministic Orders
        today = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Order patterns
        # Rahul: Maggi + Coke lover, Ice Tea enthusiast
        # Priya: Healthy-ish (Sandwich + Coffee), occasional Ice Tea + Chicken Strips
        # Amit: Heavy buyer (Pasta + Milkshake + Chicken Strips + Ice Tea)
        # Neha: New customer ordering Chicken Strips + Ice Tea
        # Vikram: Dormant customer

        counter = [100]
        def make_order(cust_idx, days_ago, hour, items, status="COMPLETED"):
            c = customers[cust_idx]
            dt = today - timedelta(days=days_ago) + timedelta(hours=hour)
            
            counter[0] += 1
            code = f"DM{counter[0]}"
            
            subtotal = sum(menu_items[name] for name in items)
            order = Order(
                customer_id=c.id,
                code=code,
                status=status,
                payment_state="VERIFIED",
                fulfilment_type="takeout",
                total_paise=subtotal,
                payable_paise=subtotal,
                created_at=dt,
                paid_at=dt + timedelta(minutes=2),
                inventory_deducted=True,
            )
            session.add(order)
            session.flush()

            for name in items:
                oi = OrderItem(
                    order_id=order.id,
                    item_id=None,
                    name_snapshot=name,
                    qty=1,
                    unit_price_paise=menu_items[name],
                    line_total_paise=menu_items[name]
                )
                session.add(oi)

        # 4. Generate history
        # Heavy Chicken Strips + Ice Tea pairing across multiple days and customers
        for d in range(7):
            # Amit orders Chicken Strips + Ice Tea daily at 5 PM (Snack time)
            make_order(2, d, 17, ["Chicken Strips", "Ice Tea"])
            make_order(2, d, 14, ["Pasta", "Milkshake"])
            make_order(2, d, 20, ["Maggi", "Coke"])

        # Rahul (Chicken Strips + Ice Tea + Maggi)
        for d in [0, 1, 2, 4, 5, 6]:
            make_order(0, d, 16, ["Chicken Strips", "Ice Tea"])
            make_order(0, d, 21, ["Maggi", "Coke"])
        make_order(0, 3, 21, ["Maggi", "Coke", "Chips"])
        
        # Priya (Sandwich + Coffee & Chicken Strips + Ice Tea)
        for d in [1, 2, 3, 5, 6]:
            make_order(1, d, 10, ["Sandwich", "Coffee"])
            make_order(1, d, 18, ["Chicken Strips", "Ice Tea"])

        # Neha (New) - loves Chicken Strips + Ice Tea
        make_order(3, 0, 15, ["Chicken Strips", "Ice Tea"])
        make_order(3, 1, 16, ["Chicken Strips"])

        # Vikram (Dormant)
        make_order(4, 20, 13, ["Sandwich", "Coffee"])
        make_order(4, 21, 13, ["Chicken Strips", "Ice Tea"])
        make_order(4, 25, 14, ["Maggi", "Coke"])

        # Today's pending/exceptions to show on dashboard
        make_order(0, 0, 19, ["Chicken Strips", "Ice Tea"], status="AWAITING_PAYMENT")
        
        # 5. Inventory Setup
        session.add(Inventory(item_name="Chicken Strips", current_stock=12, low_stock_threshold=25, target_stock=100))
        session.add(Inventory(item_name="Ice Tea", current_stock=15, low_stock_threshold=30, target_stock=120))
        session.add(Inventory(item_name="Maggi", current_stock=8, low_stock_threshold=20, target_stock=100))
        session.add(Inventory(item_name="Coke", current_stock=45, low_stock_threshold=20, target_stock=100))
        session.add(Inventory(item_name="Pasta", current_stock=4, low_stock_threshold=10, target_stock=30))
        session.add(Inventory(item_name="Coffee", current_stock=80, low_stock_threshold=30, target_stock=150))

        # 6. Promotion
        session.add(Promotion(
            name="Evening Chill Combo",
            offer_type="bundle",
            item_ids=[],
            item_names=["Chicken Strips", "Ice Tea"],
            discount_paise=rupees_to_paise(15),
            description="Buy Chicken Strips + Ice Tea for ₹15 off.",
            reason="High co-occurrence detected.",
            active=False,
            owner_approved=False,
        ))

        session.commit()
        print("Demo data seeded successfully with Chicken Strips and Ice Tea.")

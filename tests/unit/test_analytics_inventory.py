import pytest
from shopbot.analytics.inventory import get_inventory_status, update_stock
from shopbot.harness import Harness
from shopbot.models import Inventory

def test_inventory_empty():
    h = Harness()
    with h.db.session() as session:
        summary = get_inventory_status(session)
        assert summary.total_items_tracked == 0

def test_inventory_status():
    h = Harness()
    with h.db.session() as session:
        session.add(Inventory(
            item_name="Maggi",
            current_stock=5,
            low_stock_threshold=10,
            target_stock=50
        ))
        session.add(Inventory(
            item_name="Coke",
            current_stock=20,
            low_stock_threshold=10,
            target_stock=50
        ))
        session.commit()

    with h.db.session() as session:
        summary = get_inventory_status(session)
        assert summary.total_items_tracked == 2
        assert len(summary.low_stock_alerts) == 1
        assert summary.low_stock_alerts[0].item_name == "Maggi"
        assert summary.low_stock_alerts[0].status == "CRITICAL" # 5 <= 5 (default reorder)

def test_update_stock():
    h = Harness()
    with h.db.session() as session:
        inv = Inventory(item_name="Maggi", current_stock=5)
        session.add(inv)
        session.flush()
        inv_id = inv.id
        
        success = update_stock(session, inv_id, 25)
        assert success is True
        
        updated = session.get(Inventory, inv_id)
        assert updated.current_stock == 25

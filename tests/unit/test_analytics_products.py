import pytest
from shopbot.analytics.products import get_cross_sell_pairs, get_recommendations_for_order
from shopbot.harness import Harness

def test_cross_sell_empty():
    h = Harness()
    with h.db.session() as session:
        summary = get_cross_sell_pairs(session)
        assert summary.insufficient_data is True
        assert len(summary.pairs) == 0

def test_cross_sell_data():
    h = Harness()
    # We need at least MIN_ORDERS_FOR_CROSSSELL (5) to get pairs
    for i in range(5):
        h.confirm_order(f"wa{i}", "1 maggi, 1 coke", "takeout")
        order = h.get_active_order(f"wa{i}")
        h.owner_approve(order.code)

    with h.db.session() as session:
        summary = get_cross_sell_pairs(session)
        assert summary.insufficient_data is False
        assert len(summary.pairs) > 0
        pair = summary.pairs[0]
        assert {pair.source_item, pair.target_item} == {"Maggi", "Cold Drink"}
        assert pair.pair_count == 5
        assert pair.confidence == 1.0

        # test recommendations for order
        recs = get_recommendations_for_order(session, ["Maggi"])
        assert len(recs) > 0
        assert recs[0].target_item == "Cold Drink"

import pytest
from shopbot.analytics.recommendations import get_offer_recommendations
from shopbot.harness import Harness

def test_recommendations_empty():
    h = Harness()
    with h.db.session() as session:
        summary = get_offer_recommendations(session)
        assert len(summary.offer_recommendations) == 0
        assert len(summary.pending_promotions) == 0
        assert len(summary.active_promotions) == 0

# We rely on the deterministic logic tests in products and sales,
# but can add a simple integration test here if desired.

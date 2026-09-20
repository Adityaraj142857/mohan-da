"""Scenario tests driven through the Simulator channel (SPEC 15.2). Each
asserts DB state and, where relevant, the messages sent."""

from __future__ import annotations

import pytest

from shopbot.harness import Harness
from shopbot.tools.make_fake_screenshot import (
    FakeScreenshotSpec,
    expected_ocr_text,
    render_fake_screenshot,
)


@pytest.fixture
def h():
    return Harness()


def test_1_takeout_happy_path_auto_paid_via_sms(h):
    order = h.confirm_order("wa-1", "2 samosa and 1 chai", "takeout")
    assert order.status == "AWAITING_PAYMENT"
    assert order.delivery_fee_paise == 0
    assert order.total_paise == 3000

    h.simulate_exact_payment(order.code)

    order = h.get_order_by_code(order.code)
    assert order.status == "PAID"
    assert order.paid_via == "bank_sms"
    texts = h.channel.sent_texts("wa-1")
    assert any("Payment received" in t for t in texts)


def test_2_delivery_screenshot_then_sms(h):
    order = h.confirm_order("wa-2", "1 egg roll, 2 tea", "delivery", "Hostel A room 101")
    assert order.delivery_fee_paise == h.settings.delivery_fee_paise

    spec = FakeScreenshotSpec(
        amount=f"{order.payable_paise / 100:.2f}",
        utr="222233334444",
        payee=h.settings.payee_name,
        datetime_str="20 Sep 2026, 10:05 am",
    )
    outcome = h.upload_screenshot("wa-2", render_fake_screenshot(spec), register_ocr_text=expected_ocr_text(spec))
    assert outcome.verdict == "PENDING_BANK"

    h.simulate_exact_payment(order.code, utr=spec.utr)
    order = h.get_order_by_code(order.code)
    assert order.status == "PAID"
    assert order.paid_via == "bank_sms"


def test_3_screenshot_only_owner_approves_after_timeout(h):
    order = h.confirm_order("wa-3", "1 maggi", "takeout")
    spec = FakeScreenshotSpec(
        amount=f"{order.payable_paise / 100:.2f}", utr="333344445555", payee=h.settings.payee_name,
        datetime_str="20 Sep 2026, 10:05 am",
    )
    outcome = h.upload_screenshot("wa-3", render_fake_screenshot(spec), register_ocr_text=expected_ocr_text(spec))
    assert outcome.verdict == "PENDING_BANK"

    h.advance_minutes(h.settings.pending_bank_timeout_min + 1)
    h.owner_approve(order.code)

    order = h.get_order_by_code(order.code)
    assert order.status == "PAID"
    assert order.paid_via == "owner"


@pytest.mark.parametrize(
    "spec_kwargs",
    [
        {"amount": "999.00", "utr": "444400001111", "status": "success"},  # wrong amount
        {"amount": "__EXPECTED__", "utr": "444400002222", "status": "failed"},  # failed status
        {"amount": "__EXPECTED__", "utr": "444400003333", "status": "success", "payee": "Someone Else"},  # wrong payee
    ],
)
def test_4_fake_screenshot_variants_never_paid(h, spec_kwargs):
    order = h.confirm_order("wa-4", "1 coffee", "takeout")
    amount = spec_kwargs.pop("amount")
    if amount == "__EXPECTED__":
        amount = f"{order.payable_paise / 100:.2f}"
    spec_kwargs.setdefault("payee", h.settings.payee_name)
    spec = FakeScreenshotSpec(amount=amount, datetime_str="20 Sep 2026, 10:05 am", **spec_kwargs)
    outcome = h.upload_screenshot("wa-4", render_fake_screenshot(spec), register_ocr_text=expected_ocr_text(spec))
    order = h.get_order_by_code(order.code)
    assert outcome.verdict == "REJECTED_CLAIM"
    assert order.status != "PAID"


def test_4b_duplicate_image_rejected(h):
    order_a = h.confirm_order("wa-4b-a", "1 tea", "takeout")
    order_b = h.confirm_order("wa-4b-b", "1 tea", "takeout")
    spec = FakeScreenshotSpec(
        amount=f"{order_a.payable_paise / 100:.2f}", utr="555500001111", payee=h.settings.payee_name,
        datetime_str="20 Sep 2026, 10:05 am",
    )
    img = render_fake_screenshot(spec)
    h.upload_screenshot("wa-4b-a", img, register_ocr_text=expected_ocr_text(spec))
    outcome = h.upload_screenshot("wa-4b-b", img)  # same image bytes reused
    order_b = h.get_order_by_code(order_b.code)
    assert outcome.verdict == "REJECTED_CLAIM"
    assert order_b.status != "PAID"


def test_4c_duplicate_utr_flags_fraud(h):
    order_a = h.confirm_order("wa-4c-a", "1 tea", "takeout")
    order_b = h.confirm_order("wa-4c-b", "1 tea", "takeout")
    shared_utr = "666600001111"
    h.simulate_exact_payment(order_a.code, utr=shared_utr)
    spec = FakeScreenshotSpec(
        amount=f"{order_b.payable_paise / 100:.2f}", utr=shared_utr, payee=h.settings.payee_name,
        datetime_str="20 Sep 2026, 10:05 am",
    )
    outcome = h.upload_screenshot("wa-4c-b", render_fake_screenshot(spec), register_ocr_text=expected_ocr_text(spec))
    order_b = h.get_order_by_code(order_b.code)
    assert outcome.verdict == "REJECTED_CLAIM"
    assert order_b.status != "PAID"
    assert order_b.customer.fraud_flags >= 1


def test_5_underpay_needs_owner(h):
    order = h.confirm_order("wa-5a", "1 veg roll", "takeout")
    h.send_bank_sms(f"Rs {(order.payable_paise - 500) / 100:.2f} credited to A/c XXXXXX1234 UPI Ref No 700000000001. -DEMO BANK")
    order = h.get_order_by_code(order.code)
    assert order.status != "PAID"
    assert order.payment_state == "NEEDS_OWNER"


def test_5_overpay_within_tolerance_auto_matches(h):
    h2 = Harness(auto_accept_overpay_paise=200)
    order = h2.confirm_order("wa-5b", "1 veg roll", "takeout")
    h2.send_bank_sms(
        f"Rs {(order.payable_paise + 100) / 100:.2f} credited to A/c XXXXXX1234 UPI Ref No 700000000002. -DEMO BANK"
    )
    order = h2.get_order_by_code(order.code)
    assert order.status == "PAID"


def test_6_expiry_then_late_credit_needs_owner(h):
    order = h.confirm_order("wa-6", "1 samosa", "takeout")
    h.advance_minutes(h.settings.payment_ttl_min + 1)
    expired_codes = h.sweep_expiry()
    assert order.code in expired_codes

    h.simulate_exact_payment(order.code)
    order = h.get_order_by_code(order.code)
    assert order.payment_state == "NEEDS_OWNER"


def test_7_two_orders_same_total_get_distinct_payable(h):
    order_a = h.confirm_order("wa-7a", "1 samosa", "takeout")
    order_b = h.confirm_order("wa-7b", "1 samosa", "takeout")
    assert order_a.total_paise == order_b.total_paise
    assert order_a.payable_paise != order_b.payable_paise

    h.simulate_exact_payment(order_a.code)
    h.simulate_exact_payment(order_b.code)
    assert h.get_order_by_code(order_a.code).status == "PAID"
    assert h.get_order_by_code(order_b.code).status == "PAID"


def test_8_forwarder_retry_dedupe(h):
    from sqlalchemy import select

    from shopbot.models import Credit

    order = h.confirm_order("wa-8", "1 cold drink", "takeout")
    body = f"Rs {order.payable_paise / 100:.2f} credited to A/c XXXXXX1234 UPI Ref No 800000000001. -DEMO BANK"
    h.send_bank_sms(body)
    h.send_bank_sms(body)
    with h.db.session() as session:
        credits = session.scalars(select(Credit).where(Credit.utr == "800000000001")).all()
    assert len(credits) == 1
    assert h.get_order_by_code(order.code).status == "PAID"


def test_9_ambiguous_unknown_add_remove_notes_out_of_hours_blocked_dup(h):
    # unknown item -> asked, not silently dropped
    h.send_text("wa-9", "2 pizza")
    texts = h.channel.sent_texts("wa-9")
    assert any("unknown" in t.lower() for t in texts)

    # notes/modifiers preserved
    order = h.confirm_order("wa-9b", "1 chai without sugar", "takeout")
    assert order.items[0].note

    # out-of-hours

    h_closed = Harness(open_hours="00:00-00:01")
    h_closed.send_text("wa-9c", "1 tea")
    texts_closed = h_closed.channel.sent_texts("wa-9c")
    assert any("closed" in t.lower() for t in texts_closed)

    # blocked customer
    with h.db.session() as session:
        from shopbot.orders.service import get_or_create_customer

        cust = get_or_create_customer(session, "wa-9d")
        cust.blocked = True
    h.send_text("wa-9d", "1 tea")
    texts_blocked = h.channel.sent_texts("wa-9d")
    assert any("can't take this order" in t.lower() or "cant take this order" in t.lower() for t in texts_blocked)


def test_10_bank_signal_none_all_owner_confirmed(h):
    h2 = Harness(bank_signal="none")
    order = h2.confirm_order("wa-10", "1 chicken roll", "takeout")
    spec = FakeScreenshotSpec(
        amount=f"{order.payable_paise / 100:.2f}", utr="101010101010", payee=h2.settings.payee_name,
        datetime_str="20 Sep 2026, 10:05 am",
    )
    outcome = h2.upload_screenshot("wa-10", render_fake_screenshot(spec), register_ocr_text=expected_ocr_text(spec))
    assert outcome.verdict == "NEEDS_OWNER"
    h2.owner_approve(order.code)
    assert h2.get_order_by_code(order.code).status == "PAID"


def test_cancel_before_payment(h):
    h.send_text("wa-c1", "1 tea")
    h.send_text("wa-c1", "takeout")
    h.send_text("wa-c1", "yes")
    order = h.get_active_order("wa-c1")
    h.send_text("wa-c1", "cancel")
    order = h.get_order_by_code(order.code)
    assert order.status == "CANCELLED"


def test_no_price_increase_ever(h):
    """Constraint C2/C4: payable never exceeds total (discount mode default)."""
    order = h.confirm_order("wa-price", "1 chicken fried rice", "delivery", "Hostel A room 1")
    assert order.payable_paise <= order.total_paise

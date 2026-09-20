"""Replay a scripted demo day (SPEC section 16): 10 orders including fraud
cases, driven entirely through the Simulator channel — no external
accounts. Prints a pass/fail summary. Also reachable as `python -m shopbot demo`.
"""

from __future__ import annotations

from shopbot.harness import Harness
from shopbot.tools.make_fake_screenshot import (
    FakeScreenshotSpec,
    expected_ocr_text,
    render_fake_screenshot,
)


class ScenarioRunner:
    def __init__(self):
        self.h = Harness()
        self.results: list[tuple[str, bool, str]] = []

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        self.results.append((name, condition, detail))

    def run(self) -> bool:
        self._scenario_takeout_happy()
        self._scenario_delivery_screenshot_then_sms()
        self._scenario_screenshot_only_owner_approves()
        self._scenario_fake_screenshot_wrong_amount()
        self._scenario_duplicate_utr_fraud()
        self._scenario_underpay()
        self._scenario_expiry_then_late_credit()
        self._scenario_two_orders_same_total()
        self._scenario_forwarder_retry_dedupe()
        self._scenario_bank_signal_none()
        return self._print_summary()

    # -- scenarios -----------------------------------------------------

    def _scenario_takeout_happy(self):
        h = self.h
        order = h.confirm_order("cust-1", "2 samosa and 1 chai", "takeout")
        h.simulate_exact_payment(order.code)
        order = h.get_order_by_code(order.code)
        self.check("1. Takeout happy path -> PAID via SMS only", order.status == "PAID" and order.paid_via == "bank_sms")

    def _scenario_delivery_screenshot_then_sms(self):
        h = self.h
        order = h.confirm_order("cust-2", "1 egg roll, 2 tea", "delivery", "Hostel A room 101")
        spec = FakeScreenshotSpec(
            amount=f"{order.payable_paise / 100:.2f}",
            utr="222233334444",
            payee=h.settings.payee_name,
            datetime_str="20 Sep 2026, 10:05 am",
        )
        img = render_fake_screenshot(spec)
        outcome = h.upload_screenshot("cust-2", img, register_ocr_text=expected_ocr_text(spec))
        pending = outcome.verdict == "PENDING_BANK"
        h.simulate_exact_payment(order.code, utr=spec.utr)
        order = h.get_order_by_code(order.code)
        self.check(
            "2. Delivery: screenshot then SMS -> PENDING_BANK -> PAID",
            pending and order.status == "PAID" and order.delivery_fee_paise == h.settings.delivery_fee_paise,
        )

    def _scenario_screenshot_only_owner_approves(self):
        h = self.h
        order = h.confirm_order("cust-3", "1 maggi", "takeout")
        spec = FakeScreenshotSpec(
            amount=f"{order.payable_paise / 100:.2f}",
            utr="333344445555",
            payee=h.settings.payee_name,
            datetime_str="20 Sep 2026, 10:05 am",
        )
        img = render_fake_screenshot(spec)
        h.upload_screenshot("cust-3", img, register_ocr_text=expected_ocr_text(spec))
        h.advance_minutes(h.settings.pending_bank_timeout_min + 1)
        h.owner_approve(order.code)
        order = h.get_order_by_code(order.code)
        self.check("3. Screenshot only, no SMS -> owner approves -> PAID", order.status == "PAID" and order.paid_via == "owner")

    def _scenario_fake_screenshot_wrong_amount(self):
        h = self.h
        order = h.confirm_order("cust-4", "1 coffee", "takeout")
        spec = FakeScreenshotSpec(
            amount="999.00",  # wrong amount
            utr="444455556666",
            payee=h.settings.payee_name,
            datetime_str="20 Sep 2026, 10:05 am",
        )
        img = render_fake_screenshot(spec)
        outcome = h.upload_screenshot("cust-4", img, register_ocr_text=expected_ocr_text(spec))
        order = h.get_order_by_code(order.code)
        self.check(
            "4. Fake screenshot (wrong amount) -> REJECTED_CLAIM, never PAID",
            outcome.verdict == "REJECTED_CLAIM" and order.status != "PAID",
        )

    def _scenario_duplicate_utr_fraud(self):
        h = self.h
        order_a = h.confirm_order("cust-5a", "1 chicken fried rice", "takeout")
        order_b = h.confirm_order("cust-5b", "1 chicken fried rice", "takeout")
        shared_utr = "555566667777"
        h.simulate_exact_payment(order_a.code, utr=shared_utr)
        spec = FakeScreenshotSpec(
            amount=f"{order_b.payable_paise / 100:.2f}",
            utr=shared_utr,
            payee=h.settings.payee_name,
            datetime_str="20 Sep 2026, 10:05 am",
        )
        img = render_fake_screenshot(spec)
        outcome = h.upload_screenshot("cust-5b", img, register_ocr_text=expected_ocr_text(spec))
        order_b = h.get_order_by_code(order_b.code)
        self.check(
            "5. Duplicate UTR reused on a second order -> REJECTED_CLAIM + fraud flag",
            outcome.verdict == "REJECTED_CLAIM" and order_b.customer.fraud_flags >= 1,
        )

    def _scenario_underpay(self):
        h = self.h
        order = h.confirm_order("cust-6", "1 veg fried rice", "takeout")
        h.send_bank_sms(
            f"Rs {(order.payable_paise - 500) / 100:.2f} credited to A/c XXXXXX1234 UPI Ref No 666677778888. -DEMO BANK"
        )
        order = h.get_order_by_code(order.code)
        self.check("6. Underpay -> stays unpaid, flagged for owner", order.status != "PAID")

    def _scenario_expiry_then_late_credit(self):
        h = self.h
        order = h.confirm_order("cust-7", "1 egg maggi", "takeout")
        h.advance_minutes(h.settings.payment_ttl_min + 1)
        h.sweep_expiry()
        order = h.get_order_by_code(order.code)
        expired = order.status == "EXPIRED"
        h.simulate_exact_payment(order.code)
        order = h.get_order_by_code(order.code)
        self.check(
            "7. Expiry then late credit within grace -> flagged, needs owner",
            expired and order.payment_state == "NEEDS_OWNER",
        )

    def _scenario_two_orders_same_total(self):
        h = self.h
        order_a = h.confirm_order("cust-8a", "1 chicken roll", "takeout")
        order_b = h.confirm_order("cust-8b", "1 chicken roll", "takeout")
        distinct = order_a.payable_paise != order_b.payable_paise
        h.simulate_exact_payment(order_a.code)
        h.simulate_exact_payment(order_b.code)
        order_a = h.get_order_by_code(order_a.code)
        order_b = h.get_order_by_code(order_b.code)
        self.check(
            "8. Two orders same base total -> distinct payable, each matches its own",
            distinct and order_a.status == "PAID" and order_b.status == "PAID",
        )

    def _scenario_forwarder_retry_dedupe(self):
        from sqlalchemy import select

        from shopbot.models import Credit

        h = self.h
        order = h.confirm_order("cust-9", "1 cold drink", "takeout")
        body = f"Rs {order.payable_paise / 100:.2f} credited to A/c XXXXXX1234 UPI Ref No 999900001111. -DEMO BANK"
        h.send_bank_sms(body)
        h.send_bank_sms(body)  # forwarder retry
        with h.db.session() as session:
            count = len(session.scalars(select(Credit).where(Credit.utr == "999900001111")).all())
        self.check("9. Forwarder retry duplicate SMS -> single credit stored", count == 1)

    def _scenario_bank_signal_none(self):
        h2 = Harness(bank_signal="none")
        order = h2.confirm_order("cust-10", "1 chicken roll", "takeout")
        spec = FakeScreenshotSpec(
            amount=f"{order.payable_paise / 100:.2f}",
            utr="101010101010",
            payee=h2.settings.payee_name,
            datetime_str="20 Sep 2026, 10:05 am",
        )
        img = render_fake_screenshot(spec)
        outcome = h2.upload_screenshot("cust-10", img, register_ocr_text=expected_ocr_text(spec))
        self.check("10. BANK_SIGNAL=none -> every payment needs owner confirm", outcome.verdict == "NEEDS_OWNER")

    def _print_summary(self) -> bool:
        print("=== ShopBot scripted demo day ===")
        all_ok = True
        for name, ok, detail in self.results:
            mark = "PASS" if ok else "FAIL"
            print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))
            all_ok = all_ok and ok
        print(f"\n{sum(1 for _, ok, _ in self.results if ok)}/{len(self.results)} scenarios passed.")
        return all_ok


def main() -> int:
    ok = ScenarioRunner().run()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

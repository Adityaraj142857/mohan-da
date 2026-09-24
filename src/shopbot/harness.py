"""Shared test/demo harness. Not part of the SPEC repo layout — added so
`tools/seed_demo.py` (SPEC 16) and the pytest scenario suite (SPEC 15.2)
drive the exact same engine/DB/channel wiring without duplicating setup
code. See docs/DECISIONS.md for this deviation."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

from shopbot.channels.simulator import SimulatorChannel
from shopbot.clock import FakeClock
from shopbot.config import REPO_ROOT, Settings
from shopbot.conversation.engine import ConversationEngine, Outbound
from shopbot.conversation.templates import Templates
from shopbot.db import Database
from shopbot.menu.loader import load_menu_yaml, seed_menu
from shopbot.models import Order
from shopbot.notify.console import ConsoleNotifier
from shopbot.orders.service import mark_paid
from shopbot.payments.expiry import sweep_expirations
from shopbot.verify.credits import ingest_and_match
from shopbot.verify.screenshot.ocr.fake import FakeOcrEngine
from shopbot.verify.screenshot.pipeline import verify_screenshot


class Harness:
    def __init__(self, **settings_overrides):
        self._tmp_db = tempfile.mkstemp(suffix=".db")[1]
        self.media_dir = Path(tempfile.mkdtemp())
        defaults = {
            "db_path": self._tmp_db,
            "sms_webhook_secret": "test-secret",
            "admin_password": "test-admin",
            "channel": "simulator",
            "ocr_engine": "fake",
            "unique_amount_mode": "discount",
            "unique_paise_max": 30,
            "payment_ttl_min": 15,
            "late_credit_grace_min": 30,
            "bank_signal": "sms",
            "hostels": "Hostel A,Hostel B",
            "upi_vpa": "shop@bank",
            "payee_name": "Demo Shop Owner",
        }
        defaults.update(settings_overrides)
        # _env_file=None: isolate from the real shop's .env (this harness
        # backs both the test suite and `shopbot demo`, and must behave the
        # same regardless of what the owner has configured for production).
        self.settings = Settings(_env_file=None, **defaults)
        self.db = Database(self.settings)
        self.db.create_all()
        self.clock = FakeClock(datetime(2026, 9, 20, 10, 0, tzinfo=UTC))
        self.templates = Templates(REPO_ROOT / "messages.yaml")
        self.notifier = ConsoleNotifier()
        self.engine = ConversationEngine(self.settings, self.templates, self.clock, self.notifier)
        self.channel = SimulatorChannel()
        self.ocr = FakeOcrEngine()

        with self.db.session() as session:
            menu = load_menu_yaml(Path(__file__).with_name("demo_menu.yaml"))
            seed_menu(session, menu)

    # -- conversation ---------------------------------------------------

    def send_text(self, wa_id: str, text: str) -> list[Outbound]:
        self.channel.log_inbound_text(wa_id, text)
        with self.db.session() as session:
            result = self.engine.handle_text(session, wa_id, text)
        for m in result.messages:
            if m.kind == "text":
                self.channel.send_text(wa_id, m.text)
            else:
                self.channel.send_image(wa_id, m.image_bytes or b"", m.caption)
        return result.messages

    def confirm_order(self, wa_id: str, items_text: str, fulfilment_text: str, address_text: str | None = None, note_text: str = "no"):
        self.send_text(wa_id, items_text)
        self.send_text(wa_id, fulfilment_text)
        if address_text:
            self.send_text(wa_id, address_text)
        self.send_text(wa_id, note_text)  # answers "any special instructions?"; "no" skips
        self.send_text(wa_id, "yes")
        return self.get_active_order(wa_id)

    def get_active_order(self, wa_id: str) -> Order | None:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        with self.db.session() as session:
            from shopbot.models import Conversation

            conv = session.get(Conversation, wa_id)
            if not conv or not (conv.context or {}).get("order_id"):
                return None
            order_id = conv.context["order_id"]
            return session.scalar(
                select(Order)
                .options(selectinload(Order.items), selectinload(Order.customer))
                .where(Order.id == order_id)
            )

    def get_order_by_code(self, code: str) -> Order | None:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        with self.db.session() as session:
            return session.scalar(
                select(Order)
                .options(selectinload(Order.items), selectinload(Order.customer))
                .where(Order.code == code)
            )

    # -- payments ---------------------------------------------------------

    def send_bank_sms(self, body: str, sender: str = "VM-DEMOBK", received_at: datetime | None = None):
        with self.db.session() as session:
            ingest, matched_order = ingest_and_match(
                session,
                sender,
                body,
                received_at or self.clock.now(),
                self.settings.bank_sms_senders,
                self.clock,
                grace_minutes=self.settings.late_credit_grace_min,
                overpay_tolerance_paise=self.settings.auto_accept_overpay_paise,
                notifier=self.notifier,
            )
            if matched_order:
                conv_wa_id = matched_order.customer.wa_id
                text = self.templates.render("paid", code=matched_order.code, eta="Preparing now.")
                self.channel.send_text(conv_wa_id, text)
        return ingest

    def simulate_exact_payment(self, order_code: str, sender: str = "VM-DEMOBK", utr: str | None = None):
        import random

        order = self.get_order_by_code(order_code)
        if order is None:
            raise ValueError(f"no such order {order_code}")
        utr = utr or "".join(random.choices("0123456789", k=12))
        rupees = order.payable_paise / 100
        body = f"Rs {rupees:.2f} credited to A/c XXXXXX1234 UPI Ref No {utr}. -DEMO BANK"
        return self.send_bank_sms(body, sender=sender)

    def upload_screenshot(self, wa_id: str, image_bytes: bytes, register_ocr_text: str | None = None):
        if register_ocr_text is not None:
            self.ocr.register(image_bytes, register_ocr_text)
        order = self.get_active_order(wa_id)
        if order is None:
            return None
        with self.db.session() as session:
            order = session.get(Order, order.id)
            outcome = verify_screenshot(
                session,
                self.settings,
                order,
                image_bytes,
                source="simulator",
                ocr_engine=self.ocr,
                clock=self.clock,
                media_dir=self.media_dir,
                notifier=self.notifier,
            )
            text = self.templates.render(outcome.message_key, code=order.code, eta="Preparing now.")
            self.channel.send_text(wa_id, text)
        return outcome

    def owner_approve(self, order_code: str):
        with self.db.session() as session:
            from sqlalchemy import select

            order = session.scalar(select(Order).where(Order.code == order_code))
            mark_paid(session, order, paid_via="owner", clock=self.clock)
            text = self.templates.render("paid", code=order.code, eta="Preparing now.")
            self.channel.send_text(order.customer.wa_id, text)

    def sweep_expiry(self):
        with self.db.session() as session:
            return sweep_expirations(session, self.clock)

    def advance_minutes(self, minutes: float) -> None:
        self.clock.advance(minutes=minutes)

"""Deterministic conversation state machine (SPEC section 8). Never depends
on an LLM. Message economy (C7): dense messages, avoid repeats."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from shopbot.clock import Clock, to_ist
from shopbot.config import Settings
from shopbot.conversation import states as st
from shopbot.conversation.templates import Templates
from shopbot.models import Conversation, MenuItem, Order, OutboundLog
from shopbot.money import format_inr
from shopbot.nlu.normalizer import normalize_text, split_segments
from shopbot.nlu.parser import MenuIndexItem, ParsedLine, parse_order
from shopbot.orders import service as orders_service
from shopbot.payments.paypage import build_pay_url
from shopbot.payments.upi import build_upi_uri


@dataclass
class Outbound:
    kind: str  # text|image
    text: str = ""
    image_bytes: bytes | None = None
    caption: str | None = None


@dataclass
class EngineResult:
    messages: list[Outbound] = field(default_factory=list)
    order: Order | None = None


_HOSTEL_ROOM_RE = re.compile(r"(?P<hostel>[a-z]+ ?[a-z]?)\s*,?\s*room\s*(?P<room>[a-z0-9]+)", re.IGNORECASE)


def _menu_index_items(menu_items: list[MenuItem]) -> list[MenuIndexItem]:
    return [
        MenuIndexItem(
            item_id=m.id,
            name=m.name,
            price_paise=m.price_paise,
            aliases=list(m.aliases or []),
            max_qty=m.max_qty,
            available=m.available,
        )
        for m in menu_items
    ]


def _parse_open_hours(open_hours: str) -> tuple[time, time]:
    start_s, _, end_s = open_hours.partition("-")
    h1, m1 = [int(x) for x in start_s.split(":")]
    h2, m2 = [int(x) for x in end_s.split(":")]
    return time(h1, m1), time(h2, m2)


def is_open_now(open_hours: str, now_ist: datetime) -> bool:
    start, end = _parse_open_hours(open_hours)
    return start <= now_ist.time() <= end


_HOSTEL_GENERIC_WORDS = {"hostel", "hall", "annexe", "house", "residence"}


def _hostel_key(hostel: str) -> str:
    """Strip generic suffix words ('Hostel', 'Hall', ...) so 'Ramanujan
    Hostel' matches a customer typing just 'Ramanujan', and 'room 211
    ramanujan' matches too — not just the exact full name."""
    words = [w for w in hostel.split() if w.lower() not in _HOSTEL_GENERIC_WORDS]
    return " ".join(words).strip().lower() or hostel.lower()


def _find_hostel(text: str, hostels: list[str]) -> str | None:
    lowered = text.lower()
    # Exact full-name match first (handles hostels whose short key would
    # otherwise be a very common word, e.g. "New Hostel").
    for hostel in hostels:
        if hostel.lower() in lowered:
            return hostel
    # Then the longest matching short key, so more specific names win.
    keyed = sorted(hostels, key=lambda h: len(_hostel_key(h)), reverse=True)
    for hostel in keyed:
        key = _hostel_key(hostel)
        if re.search(rf"\b{re.escape(key)}\b", lowered):
            return hostel
    return None


def _extract_room(text: str) -> str | None:
    m = re.search(r"room\s*([a-z0-9\-]+)", text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"\b(\d{2,4})\b", text)
    if m:
        return m.group(1)
    return None


class ConversationEngine:
    def __init__(self, settings: Settings, templates: Templates, clock: Clock, notifier=None):
        self.settings = settings
        self.templates = templates
        self.clock = clock
        self.notifier = notifier

    # -- persistence helpers -------------------------------------------------

    def _get_conv(self, session: Session, wa_id: str) -> Conversation:
        conv = session.get(Conversation, wa_id)
        if conv is None:
            conv = Conversation(wa_id=wa_id, state=st.IDLE, context={})
            session.add(conv)
            session.flush()
        return conv

    def _save_conv(self, conv: Conversation, state: str, context: dict) -> None:
        conv.state = state
        conv.context = context
        conv.updated_at = self.clock.now()

    def _log_outbound(self, session: Session, wa_id: str, kind: str, order_id: str | None = None) -> None:
        session.add(OutboundLog(wa_id=wa_id, kind=kind, order_id=order_id))

    def _menu_items(self, session: Session) -> list[MenuItem]:
        return list(session.scalars(select(MenuItem).where(MenuItem.available.is_(True)).order_by(MenuItem.sort)))

    def _menu_lines_text(self, session: Session) -> str:
        lines = []
        for m in self._menu_items(session):
            lines.append(f"- {m.name}: {format_inr(m.price_paise)}")
        return "\n".join(lines)

    # -- entry points ----------------------------------------------------------

    def handle_text(self, session: Session, wa_id: str, raw_text: str) -> EngineResult:
        conv = self._get_conv(session, wa_id)
        customer = orders_service.get_or_create_customer(session, wa_id)

        if customer.blocked:
            self._log_outbound(session, wa_id, "blocked_generic")
            if self.notifier:
                self.notifier.notify_owner("blocked_customer_message", {"wa_id": wa_id, "text": raw_text})
            return EngineResult(messages=[Outbound(kind="text", text=self.templates.render("blocked_generic"))])

        norm = normalize_text(raw_text)
        context = dict(conv.context or {})

        # Developer-only testing bypass: sending this exact keyword lets this
        # one customer conversation order at any time, ignoring OPEN_HOURS.
        # Not a SPEC feature — purely so the app can be sanity-checked
        # outside business hours during development. Never advertised to
        # real customers; has no effect on pricing, payment, or any other
        # rule. See DEV_BYPASS_KEYWORD.
        if norm == st.DEV_BYPASS_KEYWORD:
            context["dev_bypass_hours"] = True
            self._save_conv(conv, conv.state, context)
            return EngineResult(
                messages=[
                    Outbound(
                        kind="text",
                        text="🛠 Dev mode: open-hours check disabled for this chat. Order normally now.",
                    )
                ]
            )

        # Human handoff pause: if active and not expired, bot stays silent except for explicit commands.
        human_until = context.get("human_until")
        if human_until:
            until_dt = datetime.fromisoformat(human_until)
            if self.clock.now() < until_dt and norm not in st.GLOBAL_COMMANDS:
                return EngineResult(messages=[])

        if norm in st.GLOBAL_COMMANDS:
            return self._handle_global_command(session, conv, customer, context, norm)

        if not context.get("dev_bypass_hours") and not is_open_now(self.settings.open_hours, to_ist(self.clock.now())):
            self._log_outbound(session, wa_id, "out_of_hours")
            self._save_conv(conv, conv.state, context)
            return EngineResult(
                messages=[Outbound(kind="text", text=self.templates.render("out_of_hours", hours=self.settings.open_hours))]
            )

        state = conv.state or st.IDLE

        if state in (st.IDLE, st.COLLECTING, st.NEED_FULFILMENT, st.NEED_ADDRESS):
            return self._handle_collecting(session, conv, customer, context, norm, raw_text)
        if state == st.CONFIRMING:
            return self._handle_confirming(session, conv, customer, context, norm, raw_text)
        if state == st.AWAITING_PAYMENT:
            return self._handle_awaiting_payment_text(session, conv, customer, context, norm, raw_text)

        # DONE or unknown -> treat as a fresh order
        self._save_conv(conv, st.IDLE, {})
        return self._handle_collecting(session, conv, customer, {}, norm, raw_text)

    def handle_image(self, session: Session, wa_id: str, image_bytes: bytes, source: str) -> EngineResult:
        """Route an inbound image. Only meaningful during/near payment; the
        actual OCR pipeline is wired in by the caller (channel/webhook layer)
        because it needs DB + settings not owned by the engine."""
        conv = self._get_conv(session, wa_id)
        context = dict(conv.context or {})
        order_id = context.get("order_id")
        if conv.state != st.AWAITING_PAYMENT or not order_id:
            return EngineResult(
                messages=[Outbound(kind="text", text=self.templates.render("image_unexpected"))]
            )
        order = session.get(Order, order_id)
        return EngineResult(messages=[], order=order)

    # -- global commands ---------------------------------------------------

    def _handle_global_command(self, session, conv, customer, context, cmd) -> EngineResult:
        if cmd == "menu":
            text = self.templates.render("menu_text", menu_lines=self._menu_lines_text(session))
            self._save_conv(conv, conv.state, context)
            return EngineResult(messages=[Outbound(kind="text", text=text)])
        if cmd == "help":
            return EngineResult(messages=[Outbound(kind="text", text=self.templates.render("help_text"))])
        if cmd == "status":
            order_id = context.get("order_id")
            order = session.get(Order, order_id) if order_id else None
            if not order:
                return EngineResult(messages=[Outbound(kind="text", text="No active order.")])
            text = f"Order {order.code}: {order.status} (payment: {order.payment_state})"
            return EngineResult(messages=[Outbound(kind="text", text=text)])
        if cmd == "cancel":
            order_id = context.get("order_id")
            order = session.get(Order, order_id) if order_id else None
            if order and order.status == "AWAITING_PAYMENT":
                orders_service.cancel_order(session, order, "customer cancelled")
                self._save_conv(conv, st.IDLE, {})
                return EngineResult(
                    messages=[Outbound(kind="text", text=self.templates.render("cancelled", code=order.code))]
                )
            if order and order.status == "PAID":
                if self.notifier:
                    self.notifier.notify_owner("human_requested", {"wa_id": customer.wa_id, "order_code": order.code})
                return EngineResult(messages=[Outbound(kind="text", text=self.templates.render("human_notice"))])
            self._save_conv(conv, st.IDLE, {})
            return EngineResult(messages=[Outbound(kind="text", text="Nothing to cancel.")])
        if cmd == "human":
            until = (self.clock.now() + timedelta(minutes=30)).isoformat()
            context["human_until"] = until
            self._save_conv(conv, conv.state, context)
            if self.notifier:
                self.notifier.notify_owner("human_requested", {"wa_id": customer.wa_id})
            return EngineResult(messages=[Outbound(kind="text", text=self.templates.render("human_notice"))])
        if cmd == "repeat":
            last_id = context.get("last_order_id")
            last = session.get(Order, last_id) if last_id else None
            if not last:
                return EngineResult(messages=[Outbound(kind="text", text="No previous order to repeat.")])
            draft_lines = [
                {
                    "item_id": i.item_id,
                    "name": i.name_snapshot,
                    "unit_price_paise": i.unit_price_paise,
                    "qty": i.qty,
                    "note": i.note,
                }
                for i in last.items
            ]
            context = {"draft_lines": draft_lines}
            order = orders_service.create_draft_order(session, customer)
            context["order_id"] = order.id
            lines_text = self._format_lines(draft_lines)
            self._save_conv(conv, st.NEED_FULFILMENT, context)
            text = self.templates.render(
                "summary_ask_fulfilment",
                lines=lines_text,
                subtotal=self._subtotal_str(draft_lines),
                fee=self.settings.delivery_fee_paise // 100,
            )
            return EngineResult(messages=[Outbound(kind="text", text=text)])
        return EngineResult(messages=[])

    # -- collecting items ----------------------------------------------------

    def _format_lines(self, draft_lines: list[dict]) -> str:
        out = []
        for l in draft_lines:
            note = f" ({l['note']})" if l.get("note") else ""
            out.append(f"{l['qty']}x {l['name']}{note} - {format_inr(l['unit_price_paise'] * l['qty'])}")
        return "\n".join(out)

    def _subtotal_str(self, draft_lines: list[dict]) -> str:
        total = sum(l["unit_price_paise"] * l["qty"] for l in draft_lines)
        return format_inr(total)[1:]  # strip leading rupee sign, template adds "₹"

    def _handle_collecting(self, session, conv, customer, context, norm, raw_text) -> EngineResult:
        state = conv.state or st.IDLE
        draft_lines = context.get("draft_lines", [])

        if state == st.NEED_FULFILMENT:
            fulfilment = self._parse_fulfilment(norm)
            if fulfilment:
                context["fulfilment"] = fulfilment
                if fulfilment == "delivery":
                    self._save_conv(conv, st.NEED_ADDRESS, context)
                    return EngineResult(messages=[Outbound(kind="text", text=self.templates.render("need_hostel"))])
                return self._go_to_confirming(session, conv, customer, context)
            # fall through: maybe they're adding more items instead of answering
        elif state == st.NEED_ADDRESS:
            hostel = _find_hostel(raw_text, self.settings.hostel_list())
            room = _extract_room(raw_text)
            if not hostel:
                return EngineResult(
                    messages=[
                        Outbound(
                            kind="text",
                            text=self.templates.render(
                                "unknown_hostel", hostel=raw_text.strip(), hostels=", ".join(self.settings.hostel_list())
                            ),
                        )
                    ]
                )
            context["hostel"] = hostel
            context["room"] = room or "?"
            return self._go_to_confirming(session, conv, customer, context)

        # Parse as item message (also used to add items after an unresolved answer)
        menu_items = self._menu_items(session)
        menu_index = _menu_index_items(menu_items)
        text_norm = normalize_text(raw_text)
        segments = split_segments(text_norm)
        result = parse_order(text_norm, segments, menu_index)

        if result.lines:
            for line in result.lines:
                draft_lines.append(
                    {
                        "item_id": line.item_id,
                        "name": line.name,
                        "unit_price_paise": line.unit_price_paise,
                        "qty": line.qty,
                        "note": line.note,
                    }
                )
            context["draft_lines"] = draft_lines

        problems = []
        if result.unresolved:
            problems.append(f"unknown items: {', '.join(result.unresolved)}")
        for amb in result.ambiguous:
            problems.append(f'"{amb.raw_segment}" — did you mean {" / ".join(amb.candidates)}?')
        for name, requested, max_qty in result.over_max_qty:
            problems.append(f"{name}: max {max_qty} per order (you asked for {requested})")

        if not draft_lines and not problems:
            self._save_conv(conv, st.COLLECTING, context)
            return EngineResult(messages=[Outbound(kind="text", text=self.templates.render("unknown_input"))])

        if problems:
            self._save_conv(conv, st.COLLECTING, context)
            return EngineResult(messages=[Outbound(kind="text", text=" ; ".join(problems))])

        # Everything resolved: ask fulfilment in the same message.
        self._save_conv(conv, st.NEED_FULFILMENT, context)
        lines_text = self._format_lines(draft_lines)
        text = self.templates.render(
            "summary_ask_fulfilment",
            lines=lines_text,
            subtotal=self._subtotal_str(draft_lines),
            fee=self.settings.delivery_fee_paise // 100,
        )
        return EngineResult(messages=[Outbound(kind="text", text=text)])

    def _parse_fulfilment(self, norm: str) -> str | None:
        if any(w in norm for w in st.FULFILMENT_TAKEOUT):
            return "takeout"
        if any(w in norm for w in st.FULFILMENT_DELIVERY):
            return "delivery"
        return None

    def _go_to_confirming(self, session, conv, customer, context) -> EngineResult:
        draft_lines = context.get("draft_lines", [])
        fulfilment = context.get("fulfilment", "takeout")
        fee_paise = self.settings.delivery_fee_paise if fulfilment == "delivery" else 0
        subtotal = sum(l["unit_price_paise"] * l["qty"] for l in draft_lines)
        total = subtotal + fee_paise

        unique_note = ""
        if self.settings.unique_amount_mode != "off":
            payable_preview = total  # exact preview computed at confirm time; keep message honest but simple
            unique_note = ""

        lines_text = self._format_lines(draft_lines)
        text = self.templates.render(
            "summary",
            lines=lines_text,
            subtotal=self._subtotal_str(draft_lines),
            fee=fee_paise // 100,
            total=format_inr(total)[1:],
            unique_note=unique_note,
        )
        self._save_conv(conv, st.CONFIRMING, context)
        return EngineResult(messages=[Outbound(kind="text", text=text)])

    def _handle_confirming(self, session, conv, customer, context, norm, raw_text) -> EngineResult:
        if norm in st.NEGATIVES:
            self._save_conv(conv, st.IDLE, {})
            return EngineResult(messages=[Outbound(kind="text", text="No problem — reply with your order whenever you're ready.")])
        if norm not in st.AFFIRMATIVES:
            return EngineResult(messages=[Outbound(kind="text", text='Reply "yes" to confirm or "no" to cancel.')])

        draft_lines = context.get("draft_lines", [])
        fulfilment = context.get("fulfilment", "takeout")
        hostel = context.get("hostel")
        room = context.get("room")

        order = orders_service.create_draft_order(session, customer)
        parsed_lines = [
            ParsedLine(
                item_id=l["item_id"],
                name=l["name"],
                unit_price_paise=l["unit_price_paise"],
                qty=l["qty"],
                note=l.get("note"),
            )
            for l in draft_lines
        ]
        orders_service.set_order_lines(session, order, parsed_lines)
        orders_service.confirm_and_price_order(
            session,
            order,
            fulfilment=fulfilment,
            hostel=hostel,
            room=room,
            default_fee_paise=self.settings.delivery_fee_paise,
            unique_mode=self.settings.unique_amount_mode,
            unique_paise_max=self.settings.unique_paise_max,
            payment_ttl_min=self.settings.payment_ttl_min,
            clock=self.clock,
        )

        pay_url = build_pay_url(self.settings.public_base_url, order.pay_token)
        expires_ist = to_ist(order.expires_at).strftime("%I:%M %p")

        messages: list[Outbound] = []
        if pay_url:
            text = self.templates.render(
                "pay", payable=self._paise_str(order.payable_paise), pay_url=pay_url, expires=expires_ist
            )
            messages.append(Outbound(kind="text", text=text))
        else:
            upi_uri = build_upi_uri(
                self.settings.upi_vpa,
                self.settings.payee_name,
                order.payable_paise,
                order.code,
                self.settings.shop_name,
            )
            from shopbot.payments.qr import make_qr_png

            qr_png = make_qr_png(upi_uri)
            caption = (
                f"Pay {format_inr(order.payable_paise)} to {self.settings.upi_vpa} "
                f"({self.settings.payee_name}) — valid till {expires_ist}. "
                "You'll get a confirmation here as soon as it reaches us."
            )
            messages.append(Outbound(kind="image", image_bytes=qr_png, caption=caption))

        context["order_id"] = order.id
        context["last_order_id"] = order.id
        self._save_conv(conv, st.AWAITING_PAYMENT, context)
        for m in messages:
            self._log_outbound(session, customer.wa_id, m.kind, order_id=order.id)
        return EngineResult(messages=messages, order=order)

    def _paise_str(self, paise: int) -> str:
        return format_inr(paise)[1:]

    def _handle_awaiting_payment_text(self, session, conv, customer, context, norm, raw_text) -> EngineResult:
        order_id = context.get("order_id")
        order = session.get(Order, order_id) if order_id else None
        if order and order.status == "PAID":
            return EngineResult(messages=[Outbound(kind="text", text=self.templates.render("already_confirmed"))])
        return EngineResult(
            messages=[Outbound(kind="text", text="Waiting for your payment. Reply *cancel* to cancel this order.")]
        )

    # -- payment confirmation push -------------------------------------------

    def notify_paid(self, order: Order, eta: str = "Preparing now.") -> Outbound:
        return Outbound(kind="text", text=self.templates.render("paid", code=order.code, eta=eta))

    def notify_claim_pending(self) -> Outbound:
        return Outbound(kind="text", text=self.templates.render("claim_pending"))

    def notify_claim_needs_owner(self) -> Outbound:
        return Outbound(kind="text", text=self.templates.render("claim_needs_owner"))

    def notify_claim_rejected(self) -> Outbound:
        return Outbound(kind="text", text=self.templates.render("claim_rejected"))

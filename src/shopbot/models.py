"""SQLAlchemy ORM models (SPEC section 6). All money is integer paise, all
timestamps are UTC. `events` is an append-only audit log for every state
change and decision, as required by SPEC C7/section 14."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator):
    """SQLite has no real timezone-aware storage: plain DateTime(timezone=True)
    silently round-trips as naive. We always work in UTC (SPEC section 6),
    so store naive UTC and re-attach tzinfo=utc on read, keeping every
    datetime in application code timezone-aware and comparable."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is not None:
            value = value.astimezone(UTC).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


# Order status / payment-state enums are plain strings (not DB enums) so the
# state machine module can validate transitions and tests can assert on them
# without fighting SQLite's weak enum support.
ORDER_STATUSES = (
    "DRAFT",
    "AWAITING_PAYMENT",
    "PAID",
    "PREPARING",
    "READY",
    "OUT_FOR_DELIVERY",
    "COMPLETED",
    "EXPIRED",
    "CANCELLED",
)
PAYMENT_STATES = (
    "NONE",
    "CLAIMED",
    "PENDING_BANK",
    "NEEDS_OWNER",
    "VERIFIED",
    "REJECTED_CLAIM",
    "PAID_UNVERIFIED",
)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    wa_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    default_hostel: Mapped[str | None] = mapped_column(String, nullable=True)
    default_room: Mapped[str | None] = mapped_column(String, nullable=True)
    fraud_flags: Mapped[int] = mapped_column(Integer, default=0)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)

    orders: Mapped[list[Order]] = relationship(back_populates="customer")


class MenuItem(Base):
    __tablename__ = "menu_items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String)
    price_paise: Mapped[int] = mapped_column(Integer)
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    max_qty: Mapped[int] = mapped_column(Integer, default=20)
    sort: Mapped[int] = mapped_column(Integer, default=0)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String, unique=True, index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"))
    status: Mapped[str] = mapped_column(String, default="DRAFT")
    payment_state: Mapped[str] = mapped_column(String, default="NONE")
    fulfilment_type: Mapped[str | None] = mapped_column(String, nullable=True)  # takeout|delivery
    hostel: Mapped[str | None] = mapped_column(String, nullable=True)
    room: Mapped[str | None] = mapped_column(String, nullable=True)
    address_note: Mapped[str | None] = mapped_column(String, nullable=True)
    subtotal_paise: Mapped[int] = mapped_column(Integer, default=0)
    delivery_fee_paise: Mapped[int] = mapped_column(Integer, default=0)
    total_paise: Mapped[int] = mapped_column(Integer, default=0)
    unique_adjust_paise: Mapped[int] = mapped_column(Integer, default=0)
    payable_paise: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    pay_token: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    paid_via: Mapped[str | None] = mapped_column(String, nullable=True)
    matched_credit_id: Mapped[str | None] = mapped_column(String, nullable=True)

    customer: Mapped[Customer] = relationship(back_populates="orders")
    items: Mapped[list[OrderItem]] = relationship(back_populates="order", cascade="all, delete-orphan")
    screenshots: Mapped[list[Screenshot]] = relationship(back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"))
    item_id: Mapped[str | None] = mapped_column(String, nullable=True)
    name_snapshot: Mapped[str] = mapped_column(String)
    unit_price_paise: Mapped[int] = mapped_column(Integer)
    qty: Mapped[int] = mapped_column(Integer)
    line_total_paise: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(String, nullable=True)

    order: Mapped[Order] = relationship(back_populates="items")


class Credit(Base):
    __tablename__ = "credits"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    source: Mapped[str] = mapped_column(String)  # sms|manual
    sender: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_redacted: Mapped[str] = mapped_column(String)
    raw_hash: Mapped[str] = mapped_column(String, unique=True)
    amount_paise: Mapped[int] = mapped_column(Integer)
    utr: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)
    payer_hint: Mapped[str | None] = mapped_column(String, nullable=True)
    bank: Mapped[str | None] = mapped_column(String, nullable=True)
    direction: Mapped[str] = mapped_column(String)  # credit|debit|ignored
    txn_time: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)
    status: Mapped[str] = mapped_column(String, default="UNMATCHED")
    matched_order_id: Mapped[str | None] = mapped_column(String, nullable=True)
    match_method: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)


class Screenshot(Base):
    __tablename__ = "screenshots"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"))
    source: Mapped[str] = mapped_column(String)  # whatsapp|paypage|simulator
    file_path: Mapped[str] = mapped_column(String)
    sha256: Mapped[str] = mapped_column(String)
    phash: Mapped[str | None] = mapped_column(String, nullable=True)
    ocr_text: Mapped[str | None] = mapped_column(String, nullable=True)
    extracted: Mapped[dict] = mapped_column(JSON, default=dict)
    checks: Mapped[dict] = mapped_column(JSON, default=dict)
    bank_cross_check: Mapped[str | None] = mapped_column(String, nullable=True)
    verdict: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)

    order: Mapped[Order] = relationship(back_populates="screenshots")

    __table_args__ = (UniqueConstraint("order_id", "sha256", name="uq_screenshot_per_order"),)


class Conversation(Base):
    __tablename__ = "conversations"

    wa_id: Mapped[str] = mapped_column(String, primary_key=True)
    state: Mapped[str] = mapped_column(String, default="IDLE")
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)


class EventLog(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    ts: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)
    type: Mapped[str] = mapped_column(String)
    order_id: Mapped[str | None] = mapped_column(String, nullable=True)
    customer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class OutboundLog(Base):
    __tablename__ = "outbound_log"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    ts: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)
    wa_id: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)
    order_id: Mapped[str | None] = mapped_column(String, nullable=True)


class InboundMessageLog(Base):
    """Idempotency ledger for inbound channel messages (SPEC 8.4, 13.2)."""

    __tablename__ = "inbound_message_log"

    message_id: Mapped[str] = mapped_column(String, primary_key=True)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)

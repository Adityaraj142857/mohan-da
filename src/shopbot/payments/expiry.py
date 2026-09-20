"""Background expiry sweep (SPEC 10.4): every 30s in production, or called
directly by tests / the simulator's time-warp control."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from shopbot.clock import Clock
from shopbot.models import EventLog, Order

logger = logging.getLogger(__name__)


def sweep_expirations(session: Session, clock: Clock) -> list[str]:
    """Move AWAITING_PAYMENT orders past expires_at to EXPIRED. Returns the
    list of order codes that were expired. Does not touch the unique-amount
    ledger directly — allocation always recomputes from live order state."""
    now = clock.now()
    expired_codes = []
    orders = session.scalars(
        select(Order).where(Order.status == "AWAITING_PAYMENT", Order.expires_at.isnot(None))
    ).all()
    for order in orders:
        if order.expires_at and order.expires_at <= now:
            order.status = "EXPIRED"
            session.add(EventLog(type="order_expired", order_id=order.id, payload={"code": order.code}))
            expired_codes.append(order.code)
    return expired_codes


def is_within_late_grace(order: Order, txn_time: datetime, grace_minutes: int) -> bool:
    if not order.expires_at:
        return False
    return order.expires_at <= txn_time <= order.expires_at + timedelta(minutes=grace_minutes)


async def run_expiry_loop(db, clock: Clock, interval_seconds: float = 30.0) -> None:
    """Long-running background task; started from the FastAPI lifespan."""
    while True:
        try:
            with db.session() as session:
                expired = sweep_expirations(session, clock)
                if expired:
                    logger.info("expired orders: %s", expired)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("expiry sweep failed")
        await asyncio.sleep(interval_seconds)

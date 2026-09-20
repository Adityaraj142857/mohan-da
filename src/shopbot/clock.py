"""Time handling: store UTC, display/parse Asia/Kolkata. Testable via an
injectable Clock so scenario tests can time-warp (see SPEC 13.1)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


class Clock:
    """Real clock. Tests use FakeClock instead."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FakeClock(Clock):
    """A controllable clock for tests and the simulator's time-warp control."""

    def __init__(self, start: datetime | None = None):
        self._now = start or datetime.now(UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, **timedelta_kwargs) -> None:
        self._now += timedelta(**timedelta_kwargs)

    def set(self, when: datetime) -> None:
        self._now = when


def to_ist(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(IST)


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()

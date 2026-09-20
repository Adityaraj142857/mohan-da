"""Unique-amount allocation (SPEC 11.3). Gives each pending order a distinct
payable amount so a bank credit matches exactly one order, without ever
charging a customer more than `total` (discount is the default mode)."""

from __future__ import annotations


def allocate_unique_paise(
    used_by_other_pending_orders: set[int], max_paise: int
) -> int | None:
    """Return the smallest unused adjustment k in [0, max_paise], or None if
    the whole range is exhausted (caller should widen the range by 10 or
    fall back to mode 'off' for this order, per SPEC 11.3)."""
    for k in range(max_paise + 1):
        if k not in used_by_other_pending_orders:
            return k
    return None

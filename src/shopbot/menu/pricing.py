"""Pure pricing functions (SPEC section 7). No I/O, no DB — 100% unit-tested.
Money is integer paise throughout."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PricedLine:
    name: str
    unit_price_paise: int
    qty: int

    @property
    def line_total_paise(self) -> int:
        return self.unit_price_paise * self.qty


def subtotal_paise(lines: list[PricedLine]) -> int:
    return sum(line.line_total_paise for line in lines)


def delivery_fee_paise(
    fulfilment: str,
    hostel: str | None,
    default_fee_paise: int,
    per_hostel_fee_paise: dict[str, int] | None = None,
) -> int:
    if fulfilment != "delivery":
        return 0
    per_hostel_fee_paise = per_hostel_fee_paise or {}
    if hostel and hostel in per_hostel_fee_paise:
        return per_hostel_fee_paise[hostel]
    return default_fee_paise


def total_paise(subtotal: int, delivery_fee: int) -> int:
    """total = subtotal + delivery_fee. No other charges (rule 3)."""
    return subtotal + delivery_fee


def payable_paise(total: int, unique_adjust_paise: int, mode: str) -> int:
    """Apply the unique-amount adjustment (SPEC 11.3). `unique_adjust_paise`
    is always a non-negative magnitude; `mode` decides the sign."""
    if mode == "off":
        return total
    if mode == "discount":
        return total - unique_adjust_paise
    if mode == "surcharge":
        return total + unique_adjust_paise
    raise ValueError(f"unknown unique-amount mode: {mode}")

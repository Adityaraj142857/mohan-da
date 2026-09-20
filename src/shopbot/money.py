"""Money helpers. All amounts are integer paise. Never use floats for money."""

from __future__ import annotations


def rupees_to_paise(rupees: str | float) -> int:
    """Convert a rupee amount (string or number) to integer paise, exactly."""
    if isinstance(rupees, int):
        return rupees * 100
    s = str(rupees).strip().replace(",", "")
    if "." in s:
        whole, _, frac = s.partition(".")
        frac = (frac + "00")[:2]
    else:
        whole, frac = s, "00"
    whole = whole or "0"
    sign = 1
    if whole.startswith("-"):
        sign = -1
        whole = whole[1:]
    return sign * (int(whole) * 100 + int(frac))


def paise_to_rupees_str(paise: int) -> str:
    """Format integer paise as a 2-decimal rupee string, e.g. 11463 -> '114.63'."""
    sign = "-" if paise < 0 else ""
    paise = abs(paise)
    return f"{sign}{paise // 100}.{paise % 100:02d}"


def format_inr(paise: int) -> str:
    """Format paise with a rupee sign for display, e.g. 11463 -> '₹114.63'."""
    return f"₹{paise_to_rupees_str(paise)}"

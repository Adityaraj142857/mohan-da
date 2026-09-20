"""Plain UPI deep link (SPEC 10.1). No merchant gateway, no fees."""

from __future__ import annotations

from urllib.parse import quote

from shopbot.money import paise_to_rupees_str


def build_upi_uri(
    vpa: str,
    payee_name: str,
    amount_paise: int,
    order_code: str,
    shop_name: str,
    include_tr: bool = False,
) -> str:
    amount = paise_to_rupees_str(amount_paise)
    note = f"{shop_name} {order_code}"[:40]
    params = {
        "pa": vpa,
        "pn": payee_name,
        "am": amount,
        "cu": "INR",
        "tn": note,
    }
    if include_tr:
        params["tr"] = order_code
    query = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    return f"upi://pay?{query}"

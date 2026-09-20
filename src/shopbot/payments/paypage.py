"""Pay-page token helper (SPEC 10.2). WhatsApp only makes http(s) links
tappable, so customers get an https pay-page link, not a raw upi:// link."""

from __future__ import annotations

import secrets


def new_pay_token() -> str:
    """Unguessable 16+ char URL-safe token."""
    return secrets.token_urlsafe(16)


def build_pay_url(public_base_url: str, token: str) -> str | None:
    if not public_base_url:
        return None
    return f"{public_base_url.rstrip('/')}/pay/{token}"

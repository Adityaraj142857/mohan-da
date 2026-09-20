"""QR code generation for a UPI link (SPEC 10.3)."""

from __future__ import annotations

import io

import qrcode


def make_qr_png(data: str) -> bytes:
    img = qrcode.make(data)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

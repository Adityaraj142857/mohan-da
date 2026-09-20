"""Render synthetic GPay/PhonePe/Paytm-*style* payment confirmation images
for OCR testing (SPEC 15.3). Not real app screenshots — layout only."""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

APP_COLORS = {
    "gpay": (66, 133, 244),
    "phonepe": (94, 34, 189),
    "paytm": (0, 41, 138),
    "bhim": (255, 102, 0),
}


@dataclass
class FakeScreenshotSpec:
    amount: str  # e.g. "114.63"
    utr: str  # 12 digits
    payee: str
    datetime_str: str  # e.g. "20 Sep 2026, 3:45 pm"
    status: str = "success"  # success|failed|pending
    app: str = "gpay"


def _font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype("Arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def render_fake_screenshot(spec: FakeScreenshotSpec) -> bytes:
    width, height = 720, 1280
    color = APP_COLORS.get(spec.app, (60, 60, 60))
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, width, 160], fill=color)
    draw.text((30, 60), spec.app.upper(), fill="white", font=_font(36))

    status_text = {
        "success": "Payment successful",
        "failed": "Payment failed",
        "pending": "Payment pending",
    }.get(spec.status, "Payment successful")
    draw.text((30, 220), status_text, fill=(20, 20, 20), font=_font(34))

    draw.text((30, 300), f"₹{spec.amount}", fill=(20, 20, 20), font=_font(60))
    draw.text((30, 400), f"To {spec.payee}", fill=(60, 60, 60), font=_font(28))
    draw.text((30, 460), spec.datetime_str, fill=(60, 60, 60), font=_font(26))
    draw.text((30, 540), f"UPI transaction ID: {spec.utr}", fill=(60, 60, 60), font=_font(26))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def expected_ocr_text(spec: FakeScreenshotSpec) -> str:
    """The ground-truth text a FakeOcrEngine should return for this image
    (used by tests instead of running a real OCR model)."""
    status_text = {
        "success": "Payment successful",
        "failed": "Payment failed",
        "pending": "Payment pending",
    }.get(spec.status, "Payment successful")
    return "\n".join(
        [
            spec.app.upper(),
            status_text,
            f"₹{spec.amount}",
            f"To {spec.payee}",
            spec.datetime_str,
            f"UPI transaction ID: {spec.utr}",
        ]
    )


def _cli() -> None:
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Render a synthetic payment screenshot")
    parser.add_argument("--amount", required=True)
    parser.add_argument("--utr", required=True)
    parser.add_argument("--payee", required=True)
    parser.add_argument("--datetime", dest="datetime_str", required=True)
    parser.add_argument("--status", default="success", choices=["success", "failed", "pending"])
    parser.add_argument("--app", default="gpay", choices=list(APP_COLORS))
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    spec = FakeScreenshotSpec(
        amount=args.amount,
        utr=args.utr,
        payee=args.payee,
        datetime_str=args.datetime_str,
        status=args.status,
        app=args.app,
    )
    Path(args.out).write_bytes(render_fake_screenshot(spec))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    _cli()

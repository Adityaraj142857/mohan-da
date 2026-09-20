"""Image validation, fingerprinting, and weak forensic advisories
(SPEC 11.5 steps 1-2, check C9)."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

import imagehash
from PIL import Image, UnidentifiedImageError

MAX_BYTES = 8 * 1024 * 1024
MIN_SHORT_SIDE = 300
MAX_DIMENSION = 2000
_SUSPECT_SOFTWARE = ["photoshop", "canva", "snapseed", "picsart", "gimp"]


@dataclass
class ImageValidation:
    ok: bool
    reason: str | None = None
    normalized_bytes: bytes | None = None
    sha256: str | None = None
    phash: str | None = None
    exif_software: str | None = None


def validate_and_fingerprint(image_bytes: bytes) -> ImageValidation:
    if len(image_bytes) > MAX_BYTES:
        return ImageValidation(ok=False, reason="file too large")
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
    except (UnidentifiedImageError, OSError):
        return ImageValidation(ok=False, reason="not a decodable image")

    width, height = img.size
    if min(width, height) < MIN_SHORT_SIDE:
        return ImageValidation(ok=False, reason="image too small")

    exif_software = None
    try:
        exif = img.getexif()
        if exif:
            software = exif.get(0x0131)  # Software tag
            if software:
                exif_software = str(software)
    except Exception:
        exif_software = None

    rgb = img.convert("RGB")
    if max(rgb.size) > MAX_DIMENSION:
        rgb.thumbnail((MAX_DIMENSION, MAX_DIMENSION))

    phash = str(imagehash.phash(rgb))
    sha256 = hashlib.sha256(image_bytes).hexdigest()

    buf = io.BytesIO()
    rgb.save(buf, format="JPEG", quality=90)

    return ImageValidation(
        ok=True,
        normalized_bytes=buf.getvalue(),
        sha256=sha256,
        phash=phash,
        exif_software=exif_software,
    )


def software_looks_edited(exif_software: str | None) -> bool:
    if not exif_software:
        return False
    lowered = exif_software.lower()
    return any(s in lowered for s in _SUSPECT_SOFTWARE)


def phash_distance(a: str, b: str) -> int:
    return imagehash.hex_to_hash(a) - imagehash.hex_to_hash(b)

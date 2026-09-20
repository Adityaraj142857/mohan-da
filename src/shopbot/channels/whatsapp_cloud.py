"""WhatsApp Cloud API adapter (SPEC 13.2). Official Cloud API only
(constraint C8) — no unofficial scrapers. This is a correct-by-spec
skeleton: it cannot be live-tested without a real Meta developer app, a
test number and a token (see docs/GO_LIVE.md). Off by default
(`CHANNEL=simulator`)."""

from __future__ import annotations

import hashlib
import hmac
import logging

import httpx

from shopbot.config import Settings

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.facebook.com"


def verify_webhook_signature(app_secret: str, raw_body: bytes, signature_header: str | None) -> bool:
    """Validate X-Hub-Signature-256: sha256=<hex hmac of raw body>."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    provided = signature_header.split("=", 1)[1]
    return hmac.compare_digest(expected, provided)


class WhatsAppCloudChannel:
    def __init__(self, settings: Settings):
        self.settings = settings
        version = settings.whatsapp_api_version or "v20.0"
        self.base_url = f"{GRAPH_BASE}/{version}/{settings.whatsapp_phone_number_id}"

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.settings.whatsapp_token}"}

    def send_text(self, wa_id: str, text: str) -> None:
        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "text",
            "text": {"body": text},
        }
        self._post_message(payload)

    def send_image(self, wa_id: str, image_bytes: bytes, caption: str | None = None) -> None:
        if self.settings.public_base_url:
            # Caller is expected to have already uploaded the QR and pass a
            # public link via send_text with the pay page instead; this path
            # covers ad-hoc image sends (e.g. QR fallback) via media upload.
            media_id = self._upload_media(image_bytes)
        else:
            media_id = self._upload_media(image_bytes)
        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "image",
            "image": {"id": media_id, **({"caption": caption} if caption else {})},
        }
        self._post_message(payload)

    def _post_message(self, payload: dict) -> None:
        url = f"{self.base_url}/messages"
        try:
            resp = httpx.post(url, json=payload, headers=self._headers(), timeout=10.0)
            if resp.status_code >= 400:
                logger.error("whatsapp send failed: %s %s", resp.status_code, resp.text)
        except httpx.HTTPError:
            logger.exception("whatsapp send raised")

    def _upload_media(self, image_bytes: bytes) -> str:
        url = f"{self.base_url}/media"
        files = {"file": ("qr.png", image_bytes, "image/png")}
        data = {"messaging_product": "whatsapp"}
        resp = httpx.post(url, files=files, data=data, headers=self._headers(), timeout=15.0)
        resp.raise_for_status()
        return resp.json()["id"]

    def download_media(self, media_id: str) -> bytes:
        meta_url = f"{GRAPH_BASE}/{self.settings.whatsapp_api_version or 'v20.0'}/{media_id}"
        meta = httpx.get(meta_url, headers=self._headers(), timeout=10.0)
        meta.raise_for_status()
        media_url = meta.json()["url"]
        content = httpx.get(media_url, headers=self._headers(), timeout=15.0)
        content.raise_for_status()
        return content.content


def parse_inbound_webhook(payload: dict) -> list[dict]:
    """Extract a flat list of {message_id, wa_id, type, text, media_id} from
    a Cloud API webhook payload. Ignores `statuses` entries (delivery
    receipts) per SPEC 13.2."""
    out = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []):
                item = {
                    "message_id": msg.get("id"),
                    "wa_id": msg.get("from"),
                    "type": msg.get("type"),
                }
                if msg.get("type") == "text":
                    item["text"] = msg.get("text", {}).get("body", "")
                elif msg.get("type") == "image":
                    item["media_id"] = msg.get("image", {}).get("id")
                elif msg.get("type") in ("interactive", "button"):
                    interactive = msg.get("interactive", {})
                    item["text"] = (
                        interactive.get("button_reply", {}).get("title")
                        or interactive.get("list_reply", {}).get("title")
                        or ""
                    )
                out.append(item)
    return out

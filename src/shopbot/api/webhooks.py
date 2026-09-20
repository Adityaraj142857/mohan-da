"""Bank-SMS and WhatsApp Cloud API webhooks (SPEC 11.1 Appendix E, 13.2)."""

from __future__ import annotations

import hmac
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response

from shopbot.channels.whatsapp_cloud import parse_inbound_webhook, verify_webhook_signature
from shopbot.verify.credits import ingest_and_match

logger = logging.getLogger(__name__)
router = APIRouter()


def _extract(body: dict, *keys: str):
    for key in keys:
        if key in body and body[key] not in (None, ""):
            return body[key]
    return None


def _parse_received_at(raw) -> datetime:
    if raw is None:
        return datetime.now(UTC)
    try:
        millis = float(raw)
        if millis > 10_000_000_000:  # looks like epoch ms
            millis /= 1000.0
        return datetime.fromtimestamp(millis, tz=UTC)
    except (TypeError, ValueError):
        pass
    try:
        from dateutil import parser as dateutil_parser

        return dateutil_parser.parse(str(raw))
    except (ValueError, OverflowError):
        return datetime.now(UTC)


@router.post("/webhook/bank-sms")
async def bank_sms_webhook(
    request: Request,
    x_webhook_secret: str | None = Header(default=None, alias="X-Webhook-Secret"),
    key: str | None = Query(default=None),
):
    app = request.app
    settings = app.state.settings
    provided_secret = x_webhook_secret or key or ""
    if not hmac.compare_digest(provided_secret, settings.sms_webhook_secret):
        raise HTTPException(status_code=401, detail="invalid webhook secret")

    body = await request.json()
    sender = _extract(body, "from", "sender", "address") or ""
    text = _extract(body, "text", "message", "body", "content") or ""
    received_raw = _extract(body, "receivedStamp", "received_at", "timestamp", "date")
    received_at = _parse_received_at(received_raw)

    with app.state.db.session() as session:
        ingest, matched_order = ingest_and_match(
            session,
            sender,
            text,
            received_at,
            settings.bank_sms_senders,
            app.state.clock,
            grace_minutes=settings.late_credit_grace_min,
            overpay_tolerance_paise=settings.auto_accept_overpay_paise,
            notifier=app.state.notifier,
        )
        matched_code = matched_order.code if matched_order else None
        wa_id = matched_order.customer.wa_id if matched_order else None

    if matched_order and app.state.engine:
        text_out = app.state.templates.render("paid", code=matched_code, eta="Preparing now.")
        app.state.channel.send_text(wa_id, text_out)

    return {"status": ingest.status, "matched_order": matched_code}


@router.get("/webhook/whatsapp")
async def whatsapp_verify(request: Request):
    settings = request.app.state.settings
    params = request.query_params
    if (
        params.get("hub.mode") == "subscribe"
        and params.get("hub.verify_token") == settings.whatsapp_verify_token
    ):
        return Response(content=params.get("hub.challenge", ""), media_type="text/plain")
    raise HTTPException(status_code=403, detail="verification failed")


@router.post("/webhook/whatsapp")
async def whatsapp_receive(request: Request, x_hub_signature_256: str | None = Header(default=None)):
    settings = request.app.state.settings
    raw_body = await request.body()
    if settings.whatsapp_app_secret and not verify_webhook_signature(
        settings.whatsapp_app_secret, raw_body, x_hub_signature_256
    ):
        raise HTTPException(status_code=401, detail="invalid signature")

    payload = await request.json()
    messages = parse_inbound_webhook(payload)
    app = request.app

    for msg in messages:
        message_id = msg.get("message_id")
        if not message_id:
            continue
        with app.state.db.session() as session:
            from shopbot.models import InboundMessageLog

            if session.get(InboundMessageLog, message_id):
                continue
            session.add(InboundMessageLog(message_id=message_id))

        wa_id = msg["wa_id"]
        if msg["type"] == "text":
            with app.state.db.session() as session:
                result = app.state.engine.handle_text(session, wa_id, msg.get("text", ""))
            for m in result.messages:
                if m.kind == "text":
                    app.state.channel.send_text(wa_id, m.text)
                else:
                    app.state.channel.send_image(wa_id, m.image_bytes or b"", m.caption)
        elif msg["type"] == "image":
            media_id = msg.get("media_id")
            if media_id and hasattr(app.state.channel, "download_media"):
                image_bytes = app.state.channel.download_media(media_id)
                with app.state.db.session() as session:
                    engine_result = app.state.engine.handle_image(session, wa_id, image_bytes, source="whatsapp")
                    if engine_result.order is not None:
                        from shopbot.verify.screenshot.pipeline import verify_screenshot

                        order = session.get(type(engine_result.order), engine_result.order.id)
                        outcome = verify_screenshot(
                            session,
                            app.state.settings,
                            order,
                            image_bytes,
                            source="whatsapp",
                            ocr_engine=app.state.ocr_engine,
                            clock=app.state.clock,
                            media_dir=app.state.media_dir,
                            notifier=app.state.notifier,
                        )
                        text = app.state.templates.render(outcome.message_key, code=order.code, eta="Preparing now.")
                        app.state.channel.send_text(wa_id, text)
                    else:
                        for m in engine_result.messages:
                            app.state.channel.send_text(wa_id, m.text)
        # else: unsupported inbound type -> silently ignored (SPEC 8.4 friendly nudge omitted for brevity)

    return {"status": "ok"}

"""FastAPI app factory (SPEC section 4, 10.2-10.3, 13.1)."""

from __future__ import annotations

import asyncio
import base64
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from shopbot.admin.routes import router as admin_router
from shopbot.api.webhooks import router as webhooks_router
from shopbot.channels.simulator import SimulatorChannel
from shopbot.channels.whatsapp_cloud import WhatsAppCloudChannel
from shopbot.clock import Clock, to_ist
from shopbot.config import REPO_ROOT, Settings, load_settings
from shopbot.conversation.engine import ConversationEngine
from shopbot.conversation.formatting import whatsapp_format
from shopbot.conversation.templates import Templates
from shopbot.db import Database
from shopbot.menu.loader import load_menu_yaml, seed_menu
from shopbot.models import Order
from shopbot.money import format_inr
from shopbot.notify.console import ConsoleNotifier
from shopbot.notify.telegram import TelegramNotifier
from shopbot.payments.expiry import run_expiry_loop
from shopbot.payments.qr import make_qr_png
from shopbot.payments.upi import build_upi_uri
from shopbot.verify.screenshot.ocr.factory import make_ocr_engine
from shopbot.verify.screenshot.pipeline import verify_screenshot

logger = logging.getLogger(__name__)
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "admin" / "templates"


def build_app(settings: Settings | None = None, clock: Clock | None = None) -> FastAPI:
    settings = settings or load_settings()
    clock = clock or Clock()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(run_expiry_loop(app.state.db, app.state.clock))
        try:
            yield
        finally:
            task.cancel()

    app = FastAPI(title=settings.shop_name, lifespan=lifespan)

    from starlette.middleware.sessions import SessionMiddleware

    app.add_middleware(SessionMiddleware, secret_key=settings.admin_secret_key, https_only=False)

    db = Database(settings)
    db.create_all()
    with db.session() as session:
        menu = load_menu_yaml(REPO_ROOT / "menu.yaml")
        seed_menu(session, menu)

    templates_obj = Templates(REPO_ROOT / "messages.yaml")
    jinja = Jinja2Templates(directory=str(TEMPLATES_DIR))
    jinja.env.filters["b64"] = lambda b: base64.b64encode(b).decode()
    jinja.env.filters["whatsapp_format"] = whatsapp_format

    if settings.owner_notify == "telegram":
        notifier = TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id)
    else:
        notifier = ConsoleNotifier()

    if settings.channel == "whatsapp":
        channel = WhatsAppCloudChannel(settings)
    else:
        channel = SimulatorChannel()

    engine = ConversationEngine(settings, templates_obj, clock, notifier)
    ocr_engine = make_ocr_engine(settings.ocr_engine)
    media_dir = REPO_ROOT / "media"

    app.state.settings = settings
    app.state.db = db
    app.state.clock = clock
    app.state.templates = templates_obj
    app.state.jinja = jinja
    app.state.notifier = notifier
    app.state.channel = channel
    app.state.engine = engine
    app.state.ocr_engine = ocr_engine
    app.state.media_dir = media_dir

    app.include_router(webhooks_router)
    app.include_router(admin_router)

    _register_customer_routes(app)
    return app


def _register_customer_routes(app: FastAPI) -> None:
    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    @app.get("/pay/{token}", response_class=HTMLResponse)
    async def pay_page(request: Request, token: str):
        settings = app.state.settings
        with app.state.db.session() as session:
            order = session.scalar(select(Order).where(Order.pay_token == token))
            if order is None:
                return app.state.jinja.TemplateResponse(
                    request, "pay_expired.html", {"reason": "Not found"}, status_code=404
                )
            now = app.state.clock.now()
            if order.status == "EXPIRED" or (order.expires_at and order.expires_at <= now and order.status == "AWAITING_PAYMENT"):
                return app.state.jinja.TemplateResponse(request, "pay_expired.html", {"reason": "Expired"})

            upi_uri = build_upi_uri(
                settings.upi_vpa, settings.payee_name, order.payable_paise, order.code, settings.shop_name
            )
            items = [
                {"name": i.name_snapshot, "qty": i.qty, "line_total": format_inr(i.line_total_paise)}
                for i in order.items
            ]
            ctx = {
                "shop_name": settings.shop_name,
                "order_code": order.code,
                "items": items,
                "amount": format_inr(order.payable_paise),
                "expires_at": to_ist(order.expires_at).strftime("%I:%M %p") if order.expires_at else "",
                "upi_uri": upi_uri,
                "vpa": settings.upi_vpa,
                "payee_name": settings.payee_name,
                "status": order.status,
                "token": token,
                "is_demo": settings.channel == "simulator",
            }
        return app.state.jinja.TemplateResponse(request, "pay.html", ctx)

    @app.get("/pay/{token}/status")
    async def pay_status(token: str):
        with app.state.db.session() as session:
            order = session.scalar(select(Order).where(Order.pay_token == token))
            if order is None:
                raise HTTPException(status_code=404, detail="not found")
            return {"status": order.status, "payment_state": order.payment_state}

    @app.get("/qr/{token}.png")
    async def qr_image(token: str):
        settings = app.state.settings
        with app.state.db.session() as session:
            order = session.scalar(select(Order).where(Order.pay_token == token))
            if order is None:
                raise HTTPException(status_code=404, detail="not found")
            upi_uri = build_upi_uri(
                settings.upi_vpa, settings.payee_name, order.payable_paise, order.code, settings.shop_name
            )
        return Response(content=make_qr_png(upi_uri), media_type="image/png")

    @app.post("/pay/{token}/screenshot")
    async def pay_screenshot_upload(token: str, file: UploadFile = File(...)):
        with app.state.db.session() as session:
            order = session.scalar(select(Order).where(Order.pay_token == token))
            if order is None:
                raise HTTPException(status_code=404, detail="not found")
            image_bytes = await file.read()
            outcome = verify_screenshot(
                session,
                app.state.settings,
                order,
                image_bytes,
                source="paypage",
                ocr_engine=app.state.ocr_engine,
                clock=app.state.clock,
                media_dir=app.state.media_dir,
                notifier=app.state.notifier,
            )
        return JSONResponse({"verdict": outcome.verdict})

    @app.post("/pay/{token}/simulate")
    async def pay_simulate_payment(token: str):
        """Demo-only shortcut: crafts a fake bank-credit SMS for this
        order's exact amount and runs it through the real matcher, so a
        demo doesn't require an actual UPI payment every time. Only
        available while CHANNEL=simulator — never exposed once the shop is
        wired to a real WhatsApp channel."""
        settings = app.state.settings
        if settings.channel != "simulator":
            raise HTTPException(status_code=404, detail="not found")

        import random

        from shopbot.money import paise_to_rupees_str
        from shopbot.verify.credits import ingest_and_match

        with app.state.db.session() as session:
            order = session.scalar(select(Order).where(Order.pay_token == token))
            if order is None:
                raise HTTPException(status_code=404, detail="not found")
            utr = "".join(random.choices("0123456789", k=12))
            body = (
                f"Rs {paise_to_rupees_str(order.payable_paise)} credited to A/c XXXXXX1234 "
                f"UPI Ref No {utr}. -DEMO BANK"
            )
            ingest, matched_order = ingest_and_match(
                session,
                "VM-DEMOBK",
                body,
                app.state.clock.now(),
                settings.bank_sms_senders,
                app.state.clock,
                grace_minutes=settings.late_credit_grace_min,
                overpay_tolerance_paise=settings.auto_accept_overpay_paise,
                notifier=app.state.notifier,
            )
            if matched_order:
                wa_id = matched_order.customer.wa_id
                text = app.state.templates.render("paid", code=matched_order.code, eta="Preparing now.")
        if matched_order:
            app.state.channel.send_text(wa_id, text)
        return JSONResponse({"status": ingest.status, "matched": bool(matched_order)})

    @app.get("/sim", response_class=HTMLResponse)
    async def sim_page(request: Request, wa_id: str = "cust-1"):
        channel: SimulatorChannel = app.state.channel
        history = channel.history(wa_id) if isinstance(channel, SimulatorChannel) else []
        return app.state.jinja.TemplateResponse(
            request,
            "sim.html",
            {
                "wa_id": wa_id,
                "history": history,
                "now": to_ist(app.state.clock.now()),
                "shop_name": app.state.settings.shop_name,
            },
        )

    @app.get("/sim/messages", response_class=HTMLResponse)
    async def sim_messages(request: Request, wa_id: str = "cust-1"):
        channel: SimulatorChannel = app.state.channel
        history = channel.history(wa_id) if isinstance(channel, SimulatorChannel) else []
        return app.state.jinja.TemplateResponse(
            request,
            "_sim_messages.html",
            {"history": history, "shop_name": app.state.settings.shop_name},
        )

    @app.post("/sim/send")
    async def sim_send(wa_id: str = Form(...), text: str = Form(...)):
        with app.state.db.session() as session:
            result = app.state.engine.handle_text(session, wa_id, text)
        channel: SimulatorChannel = app.state.channel
        channel.log_inbound_text(wa_id, text)
        for m in result.messages:
            if m.kind == "text":
                channel.send_text(wa_id, m.text)
            else:
                channel.send_image(wa_id, m.image_bytes or b"", m.caption)
        return PlainTextResponse("ok")

    @app.post("/sim/bank-sms")
    async def sim_bank_sms(sender: str = Form("VM-DEMOBK"), body: str = Form(...)):
        from shopbot.verify.credits import ingest_and_match

        settings = app.state.settings
        with app.state.db.session() as session:
            ingest, matched_order = ingest_and_match(
                session,
                sender,
                body,
                app.state.clock.now(),
                settings.bank_sms_senders,
                app.state.clock,
                grace_minutes=settings.late_credit_grace_min,
                overpay_tolerance_paise=settings.auto_accept_overpay_paise,
                notifier=app.state.notifier,
            )
            if matched_order:
                wa_id = matched_order.customer.wa_id
                text = app.state.templates.render("paid", code=matched_order.code, eta="Preparing now.")
                app.state.channel.send_text(wa_id, text)
        return PlainTextResponse(ingest.status)

    @app.post("/sim/time-warp")
    async def sim_time_warp(minutes: int = Form(...)):
        from shopbot.clock import FakeClock
        from shopbot.payments.expiry import sweep_expirations

        clock = app.state.clock
        if isinstance(clock, FakeClock):
            clock.advance(minutes=minutes)
            with app.state.db.session() as session:
                sweep_expirations(session, clock)
        return PlainTextResponse("ok")

"""Owner console (SPEC section 12). Password auth via session cookie, CSRF
token on POST forms, binds to 127.0.0.1 unless BIND_HOST says otherwise."""

from __future__ import annotations

import csv
import hmac
import io
from datetime import UTC, datetime

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy import select

from shopbot.menu.loader import export_menu_yaml
from shopbot.models import Credit, Customer, MenuItem, Order, Screenshot
from shopbot.money import format_inr
from shopbot.orders.service import mark_paid, transition_order
from shopbot.verify.credits import add_manual_credit, ingest_sms
from shopbot.verify.matcher import on_new_credit

router = APIRouter(prefix="/admin")

BOARD_COLUMNS = ["PAID", "PREPARING", "READY", "OUT_FOR_DELIVERY"]


def _require_admin(request: Request) -> None:
    if not request.session.get("admin_authed"):
        raise HTTPException(status_code=303, headers={"Location": "/admin/login"})


def _csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        import secrets

        token = secrets.token_urlsafe(16)
        request.session["csrf"] = token
    return token


def _check_csrf(request: Request, token: str) -> None:
    expected = request.session.get("csrf", "")
    if not expected or not hmac.compare_digest(expected, token):
        raise HTTPException(status_code=400, detail="bad csrf token")


def _render(request: Request, name: str, ctx: dict) -> HTMLResponse:
    ctx = {"csrf": _csrf_token(request), **ctx}
    return request.app.state.jinja.TemplateResponse(request, name, ctx)


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    return _render(request, "admin_login.html", {"error": None})


@router.post("/login")
async def login_submit(request: Request, password: str = Form(...)):
    settings = request.app.state.settings
    if hmac.compare_digest(password, settings.admin_password):
        request.session["admin_authed"] = True
        return RedirectResponse("/admin", status_code=303)
    return _render(request, "admin_login.html", {"error": "Wrong password"})


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)


@router.get("", response_class=HTMLResponse)
async def board(request: Request):
    _require_admin(request)
    with request.app.state.db.session() as session:
        columns = {}
        for status in BOARD_COLUMNS:
            orders = session.scalars(select(Order).where(Order.status == status).order_by(Order.paid_at)).all()
            columns[status] = [_order_card(o) for o in orders]
    return _render(request, "admin_board.html", {"columns": columns})


def _order_card(order: Order) -> dict:
    return {
        "id": order.id,
        "code": order.code,
        "status": order.status,
        "fulfilment": order.fulfilment_type,
        "hostel": order.hostel,
        "room": order.room,
        "amount": format_inr(order.payable_paise),
        "line_items": [f"{i.qty}x {i.name_snapshot}" for i in order.items],
        "customer": order.customer.wa_id if order.customer else "",
        "next_status": _next_status(order.status),
    }


def _next_status(status: str) -> str | None:
    chain = {"PAID": "PREPARING", "PREPARING": "READY", "READY": "OUT_FOR_DELIVERY", "OUT_FOR_DELIVERY": "COMPLETED"}
    return chain.get(status)


@router.post("/orders/{order_id}/advance")
async def advance_order(request: Request, order_id: str, csrf: str = Form(...)):
    _require_admin(request)
    _check_csrf(request, csrf)
    with request.app.state.db.session() as session:
        order = session.get(Order, order_id)
        if order is None:
            raise HTTPException(status_code=404)
        nxt = _next_status(order.status)
        if nxt:
            transition_order(session, order, nxt, reason="owner board action")
    return RedirectResponse("/admin", status_code=303)


@router.get("/needs-attention", response_class=HTMLResponse)
async def needs_attention(request: Request):
    _require_admin(request)
    with request.app.state.db.session() as session:
        orders = session.scalars(select(Order).where(Order.payment_state == "NEEDS_OWNER")).all()
        items = []
        for order in orders:
            shot = session.scalar(
                select(Screenshot).where(Screenshot.order_id == order.id).order_by(Screenshot.created_at.desc())
            )
            items.append(
                {
                    "order_id": order.id,
                    "code": order.code,
                    "amount": format_inr(order.payable_paise),
                    "status": order.status,
                    "checks": shot.checks if shot else {},
                    "extracted": shot.extracted if shot else {},
                    "screenshot_id": shot.id if shot else None,
                }
            )
    return _render(request, "admin_needs_attention.html", {"items": items})


@router.post("/needs-attention/{order_id}/approve")
async def approve_order(request: Request, order_id: str, csrf: str = Form(...)):
    _require_admin(request)
    _check_csrf(request, csrf)
    with request.app.state.db.session() as session:
        order = session.get(Order, order_id)
        if order is None:
            raise HTTPException(status_code=404)
        if order.status == "EXPIRED":
            order.status = "AWAITING_PAYMENT"
        mark_paid(session, order, paid_via="owner", clock=request.app.state.clock)
        wa_id = order.customer.wa_id
        text = request.app.state.templates.render("paid", code=order.code, eta="Preparing now.")
    request.app.state.channel.send_text(wa_id, text)
    return RedirectResponse("/admin/needs-attention", status_code=303)


@router.post("/needs-attention/{order_id}/reject")
async def reject_order(request: Request, order_id: str, csrf: str = Form(...)):
    _require_admin(request)
    _check_csrf(request, csrf)
    with request.app.state.db.session() as session:
        order = session.get(Order, order_id)
        if order is None:
            raise HTTPException(status_code=404)
        order.payment_state = "REJECTED_CLAIM"
        wa_id = order.customer.wa_id
        text = request.app.state.templates.render("claim_rejected")
    request.app.state.channel.send_text(wa_id, text)
    return RedirectResponse("/admin/needs-attention", status_code=303)


@router.get("/credits", response_class=HTMLResponse)
async def credits_page(request: Request):
    _require_admin(request)
    with request.app.state.db.session() as session:
        credits = session.scalars(select(Credit).order_by(Credit.received_at.desc()).limit(100)).all()
        rows = [
            {
                "id": c.id,
                "amount": format_inr(c.amount_paise),
                "utr": c.utr,
                "status": c.status,
                "direction": c.direction,
                "sender": c.sender,
                "raw": c.raw_redacted,
                "matched_order": c.matched_order_id,
            }
            for c in credits
        ]
    return _render(request, "admin_credits.html", {"credits": rows})


@router.post("/credits/paste-sms")
async def paste_sms(request: Request, sender: str = Form(...), body: str = Form(...), csrf: str = Form(...)):
    _require_admin(request)
    _check_csrf(request, csrf)
    settings = request.app.state.settings
    with request.app.state.db.session() as session:
        ingest = ingest_sms(session, sender, body, datetime.now(UTC), settings.bank_sms_senders)
        if ingest.credit:
            on_new_credit(
                session,
                ingest.credit,
                request.app.state.clock,
                grace_minutes=settings.late_credit_grace_min,
                overpay_tolerance_paise=settings.auto_accept_overpay_paise,
                notifier=request.app.state.notifier,
            )
    return RedirectResponse("/admin/credits", status_code=303)


@router.post("/credits/manual")
async def manual_credit(
    request: Request, amount_rupees: str = Form(...), utr: str = Form(""), csrf: str = Form(...)
):
    _require_admin(request)
    _check_csrf(request, csrf)
    from shopbot.money import rupees_to_paise

    settings = request.app.state.settings
    with request.app.state.db.session() as session:
        credit = add_manual_credit(
            session, rupees_to_paise(amount_rupees), utr or None, request.app.state.clock.now()
        )
        on_new_credit(
            session,
            credit,
            request.app.state.clock,
            grace_minutes=settings.late_credit_grace_min,
            overpay_tolerance_paise=settings.auto_accept_overpay_paise,
            notifier=request.app.state.notifier,
        )
    return RedirectResponse("/admin/credits", status_code=303)


@router.post("/credits/{credit_id}/dismiss")
async def dismiss_credit(request: Request, credit_id: str, csrf: str = Form(...)):
    _require_admin(request)
    _check_csrf(request, csrf)
    with request.app.state.db.session() as session:
        credit = session.get(Credit, credit_id)
        if credit:
            credit.status = "DISMISSED"
    return RedirectResponse("/admin/credits", status_code=303)


@router.get("/menu", response_class=HTMLResponse)
async def menu_page(request: Request):
    _require_admin(request)
    with request.app.state.db.session() as session:
        items = session.scalars(select(MenuItem).order_by(MenuItem.sort)).all()
        rows = [
            {"id": m.id, "name": m.name, "price": format_inr(m.price_paise), "available": m.available, "aliases": ", ".join(m.aliases or [])}
            for m in items
        ]
    return _render(request, "admin_menu.html", {"items": rows})


@router.post("/menu/{item_id}/toggle")
async def toggle_menu_item(request: Request, item_id: str, csrf: str = Form(...)):
    _require_admin(request)
    _check_csrf(request, csrf)
    with request.app.state.db.session() as session:
        item = session.get(MenuItem, item_id)
        if item:
            item.available = not item.available
    return RedirectResponse("/admin/menu", status_code=303)


@router.post("/menu/export")
async def menu_export(request: Request, csrf: str = Form(...)):
    _require_admin(request)
    _check_csrf(request, csrf)
    from shopbot.config import REPO_ROOT

    with request.app.state.db.session() as session:
        export_menu_yaml(session, REPO_ROOT / "menu.yaml", request.app.state.settings.delivery_fee_paise)
    return RedirectResponse("/admin/menu", status_code=303)


@router.get("/customers", response_class=HTMLResponse)
async def customers_page(request: Request):
    _require_admin(request)
    with request.app.state.db.session() as session:
        customers = session.scalars(select(Customer)).all()
        rows = [
            {
                "id": c.id,
                "wa_id": c.wa_id,
                "orders": len(c.orders),
                "fraud_flags": c.fraud_flags,
                "blocked": c.blocked,
            }
            for c in customers
        ]
    return _render(request, "admin_customers.html", {"customers": rows})


@router.post("/customers/{customer_id}/block")
async def toggle_block(request: Request, customer_id: str, csrf: str = Form(...)):
    _require_admin(request)
    _check_csrf(request, csrf)
    with request.app.state.db.session() as session:
        customer = session.get(Customer, customer_id)
        if customer:
            customer.blocked = not customer.blocked
    return RedirectResponse("/admin/customers", status_code=303)


@router.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request):
    _require_admin(request)
    settings = request.app.state.settings
    with request.app.state.db.session() as session:
        paid_orders = session.scalars(select(Order).where(Order.status.in_(["PAID", "PREPARING", "READY", "OUT_FOR_DELIVERY", "COMPLETED"]))).all()
        total_sales = sum(o.payable_paise for o in paid_orders)
        delivery_count = sum(1 for o in paid_orders if o.fulfilment_type == "delivery")
        takeout_count = sum(1 for o in paid_orders if o.fulfilment_type == "takeout")
        unverified = session.scalars(select(Order).where(Order.payment_state == "PAID_UNVERIFIED")).all()
        from shopbot.models import OutboundLog

        month_start = request.app.state.clock.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        outbound_count = len(session.scalars(select(OutboundLog).where(OutboundLog.ts >= month_start)).all())

    ctx = {
        "total_orders": len(paid_orders),
        "total_sales": format_inr(total_sales),
        "delivery_count": delivery_count,
        "takeout_count": takeout_count,
        "unverified_count": len(unverified),
        "outbound_count": outbound_count,
        "message_free_allowance": settings.message_free_allowance,
        "allowance_warn": outbound_count >= 0.8 * settings.message_free_allowance,
    }
    return _render(request, "admin_reports.html", ctx)


@router.get("/reports/export.csv")
async def reports_export(request: Request):
    _require_admin(request)
    with request.app.state.db.session() as session:
        orders = session.scalars(select(Order).order_by(Order.created_at)).all()
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["code", "status", "payment_state", "fulfilment", "hostel", "room", "total_paise", "payable_paise", "paid_via", "created_at", "paid_at"])
        for o in orders:
            writer.writerow(
                [o.code, o.status, o.payment_state, o.fulfilment_type, o.hostel, o.room, o.total_paise, o.payable_paise, o.paid_via, o.created_at, o.paid_at]
            )
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=orders.csv"}
    )

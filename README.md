# ShopBot

A free, WhatsApp-style ordering assistant for a small food shop, with
payments confirmed from your **bank's own credit alert** — never from a
screenshot alone. Runs on your own computer at **₹0**.

Full background: [`flow/PROBLEM_STATEMENT.md`](flow/PROBLEM_STATEMENT.md) and
the technical spec this was built from: [`flow/SPEC.md`](flow/SPEC.md).
Build notes: [`PLAN.md`](PLAN.md), deviations from the spec:
[`docs/DECISIONS.md`](docs/DECISIONS.md).

## What it does

1. A customer messages an order in plain English/Hinglish ("2 samosa and 1
   chai, hostel B room 204").
2. ShopBot prices it from your menu, adds ₹15 for delivery, and asks only
   for what's missing.
3. It sends a payment link/QR for the **exact amount**, immediately — no
   waiting, no extra owner typing.
4. As soon as your bank texts you that the money arrived, ShopBot matches it
   to the right order automatically and tells the customer "Payment
   received" — most orders need zero manual confirmation.
5. If a customer sends a payment screenshot, it's checked (amount, payee,
   status, reused/duplicate detection) — but it's a *helper*, not proof. A
   screenshot alone never marks an order paid.
6. **Business Intelligence**: The app doesn't just process orders; it learns from them. It tracks inventory, segments customers, finds cross-selling opportunities (e.g. "Maggi + Coke"), and recommends promotional offers.
7. You get a live order board, a "needs attention" queue, and a comprehensive business dashboard — all in a browser on your own machine.

## Quick start (one command)

```bash
bash start.sh
```

This single script does everything: sets up the virtual environment on
first run, starts ShopBot **and** the n8n automation pipeline in the
background (they keep running after you close the terminal), and opens
your browser straight to the simulator. Check on them any time with
`bash start.sh status`, and stop everything with `bash start.sh stop`.
Windows users: `scripts\run.bat` does the ShopBot half of this (n8n setup
is a separate manual step on Windows — see `docs/assignment/RUN_WORKFLOW.md`).

Once it's open:
- **http://127.0.0.1:8000/sim** — a WhatsApp-like chat simulator. Place an
  order, confirm it, then use the "Bank SMS injector" at the bottom to
  paste a fake bank credit SMS and watch the order flip to paid.
- **http://127.0.0.1:8000/admin** — the owner console (password printed by
  `start.sh`, also in `.env` as `ADMIN_PASSWORD`). Live board,
  needs-attention queue, bank credits, menu editor, customers, reports.
- **http://localhost:5678** — the n8n automation pipeline (course
  assignment deliverable), if Node.js/n8n are installed.

Prefer to run things manually instead? See `python -m shopbot run` in
`docs/DEPLOY_FREE.md` / `docs/GO_LIVE.md` for the underlying commands.

## Setting it up for your real shop

1. Edit `menu.yaml` with your real items, prices and aliases (how customers
   might spell them).
2. Edit `.env`:
   - `SHOP_NAME`, `UPI_VPA` (your UPI ID), `PAYEE_NAME` (exactly how your
     name shows up in GPay/PhonePe), `HOSTELS`, `DELIVERY_FEE_PAISE`.
   - Generate a real `SMS_WEBHOOK_SECRET` and `ADMIN_PASSWORD` (don't use
     the demo defaults).
3. **Bank SMS forwarding** (this is what replaces "checking a relative's
   bank statement"): install a free Android SMS-to-webhook forwarder app
   on the phone that receives your bank's credit alerts, and point it at
   `http://<this-computer's-LAN-IP>:8000/webhook/bank-sms?key=<SMS_WEBHOOK_SECRET>`.
   See [`docs/SMS_FORMATS.md`](docs/SMS_FORMATS.md) to test and tune your
   bank's exact SMS wording first with:
   ```bash
   python -m shopbot.tools.test_sms "paste your bank SMS here"
   ```
4. **A public URL** (so payment links and, later, WhatsApp's webhook work):
   see [`docs/DEPLOY_FREE.md`](docs/DEPLOY_FREE.md). Without one, ShopBot
   falls back to sending a QR image directly.
5. When you're ready to check real payment screenshots, run
   `python -m shopbot.tools.eval_screenshots <folder-of-real-screenshots>`
   and read the accuracy it reports **before** trusting it (see
   [`docs/OWNER_TODO.md`](docs/OWNER_TODO.md)).
6. To go live on WhatsApp itself (still free at low volume), follow
   [`docs/GO_LIVE.md`](docs/GO_LIVE.md).

Until you do steps 3-6, `CHANNEL=simulator` keeps everything working as a
local demo — nothing here talks to the internet or costs money by default.

## How payments are actually confirmed (the important part)

- An order is only ever marked **PAID** by (a) a matching bank credit, or
  (b) you clicking Approve in the owner console. Never by a screenshot
  alone, and never when the amounts don't match exactly.
- Every order gets a **slightly different amount to pay** (a few paise
  less than the total, by default) so that even if two customers order the
  exact same thing at the exact same time, your bank statement tells them
  apart automatically. Customers are **never charged more** than menu
  price + delivery — the shop absorbs the few paise, not the customer.
- If your phone stops forwarding bank SMS, or a screenshot doesn't check
  out, nothing is ever guessed — the order goes to your "Needs attention"
  queue instead.

## Running the tests

```bash
pip install -e ".[dev]"
pytest                 # unit + scenario tests
ruff check src tests   # linting
python -m shopbot demo # scripted end-to-end day
python -m shopbot seed-demo-analytics # generate demo data for the analytics dashboard
```

## Project layout

See `flow/SPEC.md` section 4.2 for the intended repo layout; the actual
layout matches it with the additions noted in `docs/DECISIONS.md`.

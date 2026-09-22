# Current status

_Last updated: 2026-09-22. Update this file every time something meaningful changes — new feature, bug fix, config change, or a shift in what's running/where._

## TL;DR

ShopBot (the shop's ordering + payment app) is **built, tested, and working**. The course assignment's n8n automation pipeline is **built and verified live**. Both are pushed to GitHub. Two real-world setup items are still outstanding before this could take real customer orders (see "Not done yet" below) — everything else works today.

## What's running right now (on this machine)

| Service | URL | Status |
|---|---|---|
| ShopBot (order-taking, payments, admin) | http://127.0.0.1:8000 | ✅ running |
| n8n (assignment automation pipeline) | http://localhost:5678 | ✅ running |
| Public tunnel (Cloudflare) | — | ❌ off — was unreliable, disabled for now (see below) |

Both processes get killed if the machine runs low on memory or restarts — if either URL doesn't respond, just say so and they'll be restarted. Nothing is lost when this happens; all data lives in `shopbot.db` (SQLite) and `.n8n/` on disk.

**To start them yourself:**
```bash
cd /Users/arshukla/Documents/Projects/small_scale_payment
source .venv/bin/activate && python -m shopbot run      # ShopBot
```
```bash
export PATH="/Users/arshukla/.nvm/versions/node/v22.23.2/bin:$PATH"
export N8N_USER_FOLDER="$PWD/.n8n"
export N8N_SECURE_COOKIE=false
n8n start                                                 # n8n (separate terminal)
```
Or `bash scripts/demo.sh` for ShopBot alone with automatic setup.

## What's built and working

### ShopBot (the actual shop app)
- Real menu (106 items) transcribed from MohanDa's printed menu card.
- Order parsing: English/Hinglish/romanised-Bengali, typos, quantities, modifiers.
- Pricing: menu total + ₹15 delivery, customers never pay more than that.
- Payment: UPI deep link + QR (sent as an inline image — no external link/tunnel needed).
- Payment confirmation: automatic via simulated bank-SMS matching (unique-amount trick keeps same-priced orders distinct), with a working "Simulate this payment" demo button so no real UPI transaction is needed to test.
- Screenshot fraud checks: duplicate image/UTR detection, payee/amount/status/timestamp checks — screenshot alone never marks an order paid.
- Owner console (`/admin`): live board, needs-attention queue, credits ledger, menu editor, customers, reports/CSV.
- WhatsApp-style `/sim` chat UI: real clickable links, bold text rendering, live-updating without full page reloads.
- 130 automated tests passing + a 10/10 scripted demo day (`python -m shopbot demo`).

### Course assignment (`docs/assignment/`)
- Problem Brief, Automation Argument (6-factor table → concludes a hybrid: auto-confirm exact bank-credit matches, escalate everything ambiguous to the owner), Test Results, Presentation Outline.
- n8n workflow (`n8n_workflow.json`): ingest → analyze/decide (calls ShopBot's real matcher) → branch → auto-confirm or escalate. **Verified live** — 7 test cases run through the actual pipeline, recorded in `03_TEST_RESULTS.md`.
- All docs and the workflow file are pushed to GitHub with placeholders instead of real secrets.

## Configuration state

- `.env` has real values: shop name, real UPI ID (`8602003005@amazonpay`), real hostel list (all of IIM Calcutta's residence halls), real generated secrets (admin password, session key, SMS webhook secret — rotated once after a leak was caught before pushing to GitHub).
- `.env` is **not** committed to GitHub (gitignored) — `.env.example` (structure only, placeholder values) is committed instead.
- `PUBLIC_BASE_URL` is currently **empty** — the free Cloudflare tunnel kept failing to come up reliably, so ShopBot is running in QR-image mode (orders get a QR code image directly in chat, no external link). This is fully functional for demo purposes.

## GitHub

**Repo:** https://github.com/Adityaraj142857/mohan-da
**Latest commit:** `6d675e6` — initial commit, 128 files, everything above.
No changes since — the fixes made after that (secret rotation, tunnel reliability, this file) either predate the commit or are being added now.

## Not done yet (owner's real-world setup, not code work)

1. **Confirm `PAYEE_NAME` in `.env`** — currently a guess (`MOHAN DA`); should be set to whatever name actually shows up when someone pays `8602003005@amazonpay` via GPay/PhonePe.
2. **Confirm `OPEN_HOURS`** in `.env` — currently a guess (`09:00-23:00`).
3. **Real bank SMS forwarder** — for actual customers, someone needs to install a free Android SMS-forwarder app on the phone receiving bank credit alerts and point it at ShopBot's webhook (see `docs/SMS_FORMATS.md`). Right now, payment confirmation is simulated for demo purposes.
4. **Real WhatsApp connection** — explicitly deferred by your own choice (didn't want to risk the number getting banned). Current demo uses the `/sim` chat instead of real WhatsApp; upgrading later needs `docs/GO_LIVE.md`.
5. A stable public URL (paid domain or a more reliable tunnel) if you want pay-page *links* instead of QR images — optional, not required for the QR flow to work.

## Known limitations / things to watch

- The free Cloudflare tunnel (`trycloudflare.com`) is unreliable — don't depend on it for a live demo without testing it fresh each time.
- n8n and ShopBot both get killed by the OS if system memory runs low — expected, not a bug; just restart them.

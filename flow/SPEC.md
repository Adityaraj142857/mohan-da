# SPEC: ShopBot — WhatsApp Food-Ordering Agent with Free, Bank-Verified UPI Payments

> **Audience:** Claude Code (the builder). **Owner:** a small food shop in India that sells takeout and hostel delivery.
> **Goal:** a *working dummy model* that runs on the owner's own computer at ₹0, can be demoed end to end without any external account, and can later be pointed at real WhatsApp with configuration changes only.
> Read this whole file before writing code.

---

## 0. How to work

1. **Plan first.** Write `PLAN.md` (phases → tasks → tests). Then build phase by phase (Section 16). After each phase: run tests, update `README.md`, commit.
2. **Do not ask questions this spec already answers.** Where a value is unknown (UPI ID, shop name, real menu, bank SMS format), use a clearly-marked placeholder in `.env.example` / `menu.yaml` and record it in `docs/OWNER_TODO.md`.
3. **Never enable anything that costs money by default.** No paid API is called in the default configuration. No secrets in the repo.
4. **Reality beats this spec.** If an API, library, or policy has changed, follow reality and log the deviation in `docs/DECISIONS.md`.
5. **The owner is non-technical.** Deliver: one-command setup, one-command run, one-command demo, and a plain-English `README.md`.
6. **Cross-platform.** Must run on Windows 10/11, macOS, Linux. No bash-only scripts; use Python entry points (`python -m shopbot ...`). A `run.bat` and `run.sh` wrapper are welcome.

---

## 1. The problem being solved

Today (fully manual):

1. Customer WhatsApps food item names.
2. Owner looks up prices, adds them up, asks "takeout or delivery?", adds **₹15** for delivery.
3. Owner sends a payment QR.
4. Customer sends a payment screenshot.
5. Owner checks a relative's bank statement to see whether money actually arrived.

Target:

- Customer messages naturally ("2 samosa n 1 chai, hostel B room 204").
- The system understands it, prices it from the menu, adds the delivery fee, asks for anything missing, and sends a payment link/QR for the exact amount.
- **Payment is confirmed automatically from the bank's own credit alert**, not from the screenshot.
- The screenshot flow still exists: it is checked by OCR, used to speed up and sharpen matching, and used to catch obvious fakes. It is **never** the sole proof of payment (see 3.1).
- The owner gets a live order board and alerts.

---

## 2. Hard constraints (the ₹0 rule)

| # | Constraint | Consequence |
|---|---|---|
| C1 | No payment gateway, no merchant fees | Collect via plain UPI deep link / QR to the owner's own VPA. |
| C2 | No paid LLM in the default path | Order understanding is **rule-based + fuzzy matching**. An LLM parser may exist behind an interface but is **off by default**. |
| C3 | No hosting bill | Runs on the owner's PC/laptop (or spare Android via Termux). Free tunnel for public URL. |
| C4 | Do not raise customer prices | Delivery fee stays at the owner's ₹15 (configurable). Unique-amount trick (11.3) **defaults to a tiny discount, never a surcharge**. |
| C5 | Free & open-source deps only | Permissive licenses (MIT/BSD/Apache). No accounts needed to run the demo. |
| C6 | Data stays local | SQLite + local files. No cloud DB. |
| C7 | Message economy | Design for ≤ 7 outbound WhatsApp messages per order (see 13.3) because WhatsApp's free allowance is limited. |
| C8 | No unofficial WhatsApp automation | Do **not** use WhatsApp-Web scrapers/unofficial libraries (ToS/ban risk). Official Cloud API only. |

---

## 3. Ground truths that shape the design (do not "fix" these away)

### 3.1 A payment screenshot is not proof of payment
Fake-payment generator apps and image editors produce convincing "Payment Successful" screens; reputable payment-industry guidance says a screenshot never proves a transaction and only a credit in the receiver's own bank/UPI app does. Therefore:

- **`PAID` may only be set by (a) a matched bank-credit event, or (b) an explicit owner action.** Never by OCR alone in the default configuration.
- The screenshot verifier is a **filter + matching key + owner-assist**, not a source of truth. Its purposes:
  1. Extract the **UTR** (12-digit UPI reference) so the right bank credit can be found instantly and unambiguously.
  2. Detect *obviously* wrong claims early (wrong amount, wrong payee, failed status, stale date, reused UTR, reused image) so the customer is corrected and the owner is alerted.
  3. Prepare a one-glance summary for the owner when bank confirmation isn't automatic.

### 3.2 Raw UPI links give no callback
A `upi://pay?...` deep link/QR has no webhook. A free way to learn "money arrived" is the **bank's credit SMS** (or bank email alert) on the phone that receives alerts for the collecting account. We ingest it via a free open-source Android SMS-forwarder app (Section 11.1) or manual paste/entry.

### 3.3 Whose phone gets the bank SMS matters
Bank alerts go to the **mobile number registered with the collecting account**. If the shop collects into a relative's account, the forwarder app must run on the phone holding that SIM (with that person's consent), or the shop should collect into an account/SIM the owner controls. Also: high-volume business collection on a personal UPI ID may draw bank attention; the `UPI_VPA` env var can later be swapped for a free merchant/current-account QR with **no code change**.

### 3.4 WhatsApp does not make `upi://` links tappable, and a phone can't scan its own screen
Only `http(s)` links are tappable in WhatsApp; and a customer chatting on their phone can't scan a QR shown on that same phone. Solution: send an **HTTPS "pay page"** link (`/pay/<token>`) that shows the amount, a **"Pay with UPI app"** button (opens GPay/PhonePe/Paytm via the `upi://` intent), a QR (for scanning from another device), a copy-VPA button, a live status that flips to "Payment confirmed ✅", and a screenshot upload box. If no public URL exists, fall back to sending the QR image + VPA text + exact amount.

### 3.5 WhatsApp Cloud API: free for development, limited for production
- Meta's auto-created **test number** can message **up to 5 verified recipient numbers** and costs nothing — perfect for the demo and for the owner + a few friends.
- Real customers require the owner's **own registered business number**, Meta business setup/verification, and a payment method on file with Meta. Replies inside the 24-hour customer-service window have been free; per provider blog posts, **from 1 Oct 2026 service messages become chargeable after 1,000 free per month (~₹0.145 each on one BSP)**. Treat these figures as *verify-before-launch*; therefore the system counts outbound messages (13.3).
- Therefore: the core engine is **channel-agnostic**; the web **Simulator** is the first channel; WhatsApp is an adapter.

### 3.6 Free tunnels have changing URLs
Free quick tunnels (e.g. Cloudflare `trycloudflare.com`, free ngrok) hand out random URLs that change on restart; a stable free URL usually requires owning a domain or using a free relay service. For the dummy model a changing URL is acceptable (update Meta's webhook URL after each restart). Document the options in `docs/DEPLOY_FREE.md`; `PUBLIC_BASE_URL` is a single env var.

### 3.7 Bank SMS formats differ per bank
Parsers must be **data-driven, testable, and tunable by the owner** using real (redacted) samples. Ship synthetic fixtures + a CLI to test a pasted SMS. Do not pretend the synthetic formats are universal.

### 3.8 OCR is imperfect on real screenshots
Ship synthetic-screenshot tests **and** an evaluation script the owner runs on ~20 real (redacted) screenshots to measure extraction accuracy (Section 15.4).

---

## 4. Architecture

```
 Customer (WhatsApp)                                  Owner
        │                                               │
        ▼                                               ▼
┌───────────────┐   ┌─────────────────────────────────────────────┐   ┌────────────────┐
│ Channel       │──▶│                  CORE ENGINE                │◀──│ Owner Console  │
│  • Simulator  │   │ conversation → parser → pricing → order     │   │  (web, mobile  │
│  • WhatsApp   │◀──│ payment: link/QR/pay-page, expiry           │   │   friendly)    │
│    Cloud API  │   │ verification: credits, matcher, screenshot  │   └────────────────┘
└───────────────┘   └───────▲───────────────────────▲─────────────┘            ▲
                            │                       │                          │
              POST /webhook/bank-sms       Telegram notifier (free)   SQLite (local file)
                            │
              Android "SMS forwarder" app on the phone that receives bank alerts
```

### 4.1 Stack (defaults; deviate only with a note in DECISIONS.md)

- Python 3.11+, **FastAPI** + Uvicorn, **SQLite (WAL mode)** via SQLAlchemy 2.x, Jinja2 templates, vendored `htmx` (no CDN dependency), `httpx`, `pydantic-settings`, `PyYAML`.
- Text matching: `rapidfuzz`. QR: `qrcode[pil]`. Images: `Pillow`, `imagehash`.
- OCR: **RapidOCR (`rapidocr-onnxruntime`)** as default (pip-only, no system binary) behind an `OcrEngine` interface with `TesseractEngine` (optional) and `FakeOcrEngine` (tests).
- Dates: `python-dateutil`, all storage in UTC, display/parse in `Asia/Kolkata`.
- Tests: `pytest`, `pytest-asyncio`, `ruff`.
- **Money is stored as integer paise everywhere.** Never floats.

### 4.2 Repo layout

```
shopbot/
  README.md  SPEC.md  PLAN.md  .env.example  menu.yaml  messages.yaml  pyproject.toml
  docs/  OWNER_TODO.md  DECISIONS.md  DEPLOY_FREE.md  SMS_FORMATS.md  GO_LIVE.md
  src/shopbot/
    config.py  db.py  models.py  money.py  clock.py
    menu/        loader.py  pricing.py
    nlu/         normalizer.py  parser.py  llm_parser.py(stub, off)
    conversation/ engine.py  states.py  templates.py
    orders/      service.py  codes.py
    payments/    upi.py  qr.py  unique_amount.py  paypage.py  expiry.py
    verify/      credits.py  matcher.py  sms_parsers/(generic.py, banks/*.py)
                 screenshot/(pipeline.py, extract.py, checks.py, forensics.py, ocr/*.py)
    channels/    base.py  simulator.py  whatsapp_cloud.py
    notify/      base.py  console.py  telegram.py
    admin/       routes.py  templates/*.html  static/
    api/         app.py  webhooks.py
    tools/       test_sms.py  eval_screenshots.py  seed_demo.py  make_fake_screenshot.py
  tests/  unit/  scenarios/  fixtures/(sms/, screenshots/)
  scripts/ run.bat  run.sh
```

---

## 5. Configuration (`.env`; provide `.env.example` with safe placeholders)

| Var | Default | Meaning |
|---|---|---|
| `SHOP_NAME` | `My Shop` | Shown to customers |
| `TZ` | `Asia/Kolkata` | |
| `UPI_VPA` | `yourname@bank` | Collecting UPI ID (placeholder!) |
| `PAYEE_NAME` | `SHOP OWNER NAME` | Must match how the name appears in customer apps |
| `PAYEE_NAME_ALIASES` | `` | Comma-separated extra spellings for the payee check |
| `DELIVERY_FEE_PAISE` | `1500` | ₹15 flat; optional per-hostel override in `menu.yaml` |
| `HOSTELS` | `Hostel A,Hostel B` | Deliverable locations (validated) |
| `OPEN_HOURS` | `09:00-22:00` | Outside → polite auto-reply |
| `PAYMENT_TTL_MIN` | `15` | Time to pay |
| `LATE_CREDIT_GRACE_MIN` | `30` | A credit after expiry goes to owner review |
| `UNIQUE_AMOUNT_MODE` | `discount` | `off` \| `discount` \| `surcharge` (see 11.3) |
| `UNIQUE_PAISE_MAX` | `30` | Max paise adjustment (avg loss ≈ ₹0.15/order in discount mode) |
| `BANK_SIGNAL` | `sms` | `sms` \| `none` (none ⇒ every payment goes to owner one-tap confirm) |
| `BANK_SMS_SENDERS` | `.*` | Regex of allowed SMS sender IDs (tighten for real use!) |
| `SMS_WEBHOOK_SECRET` | *(required)* | Shared secret for `/webhook/bank-sms` |
| `PENDING_BANK_TIMEOUT_MIN` | `10` | Wait for bank alert after a good screenshot |
| `SCREENSHOT_POLICY` | `owner_confirm` | `owner_confirm` \| `auto_approve_if_strong` (off by default; see 11.5) |
| `AUTO_ACCEPT_OVERPAY_PAISE` | `0` | Tolerated overpayment for auto-match |
| `OCR_ENGINE` | `rapidocr` | `rapidocr` \| `tesseract` \| `fake` |
| `NLU_MODE` | `rules` | `rules` \| `llm` (llm needs a key; off by default) |
| `CHANNEL` | `simulator` | `simulator` \| `whatsapp` |
| `PUBLIC_BASE_URL` | `` | HTTPS base for pay page/QR links (tunnel URL) |
| `ADMIN_PASSWORD` | *(required)* | Owner console |
| `BIND_HOST` | `127.0.0.1` | Set `0.0.0.0` to allow shop-LAN access |
| `OWNER_NOTIFY` | `console` | `console` \| `telegram` |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | `` | Free owner alerts |
| `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET` | `` | Cloud API |
| `WHATSAPP_API_VERSION` | `` | **Look up a currently supported Graph API version in Meta docs; do not hard-code from memory** |
| `MEDIA_RETENTION_DAYS` | `30` | Purge stored screenshots |
| `MESSAGE_FREE_ALLOWANCE` | `1000` | For the outbound-message counter warning |

---

## 6. Data model (SQLite; integer paise; UTC timestamps)

- `customers(id, wa_id UNIQUE, name, default_hostel, default_room, fraud_flags INT, blocked BOOL, created_at)`
- `menu_items(id, name, price_paise, aliases JSON, category, available BOOL, max_qty, sort)` — seeded from `menu.yaml`; availability/price editable in console.
- `orders(id, code UNIQUE, customer_id, status, payment_state, fulfilment_type, hostel, room, address_note, subtotal_paise, delivery_fee_paise, total_paise, unique_adjust_paise, payable_paise, note, pay_token UNIQUE, created_at, expires_at, paid_at, paid_via, matched_credit_id)`
  - `status`: `DRAFT → AWAITING_PAYMENT → PAID → PREPARING → READY → OUT_FOR_DELIVERY → COMPLETED`; terminal side-states `EXPIRED`, `CANCELLED`.
  - `payment_state`: `NONE | CLAIMED | PENDING_BANK | NEEDS_OWNER | VERIFIED | REJECTED_CLAIM`.
- `order_items(id, order_id, item_id, name_snapshot, unit_price_paise, qty, line_total_paise, note)`
- `credits(id, source[sms|manual], sender, raw_redacted, raw_hash UNIQUE, amount_paise, utr NULLABLE UNIQUE, payer_hint, bank, direction[credit|debit|ignored], txn_time, received_at, status[UNMATCHED|MATCHED|DISMISSED|REVERSED], matched_order_id, match_method, created_at)`
- `screenshots(id, order_id, source[whatsapp|paypage|simulator], file_path, sha256 UNIQUE-per-order-policy, phash, ocr_text, extracted JSON, checks JSON, bank_cross_check, verdict, created_at)`
- `conversations(wa_id PK, state, context JSON, updated_at)`
- `events(id, ts, type, order_id, customer_id, payload JSON)` — append-only audit log; every state change and every decision (with reasons) is logged.
- `outbound_log(id, ts, wa_id, kind, order_id)` — message counter for C7.

---

## 7. Menu & pricing

`menu.yaml` is the seed; the DB is the runtime source (console can toggle availability and edit prices; provide "export back to YAML").

```yaml
delivery_fee_paise: 1500          # ₹15 flat
delivery_fee_by_hostel: {}        # optional overrides, e.g. {"Hostel C": 2000}
items:
  - name: Tea
    price: 10
    aliases: [chai, cha, tea]
    max_qty: 20
  - name: Samosa
    price: 10
    aliases: [samosa, samosha, singara]
  - name: Egg Roll
    price: 50
    aliases: [egg roll, eggroll, e roll]
  # ... (see Appendix A for a full dummy menu)
```

**Pricing rules (all in `menu/pricing.py`, pure functions, 100% unit-tested):**
1. `subtotal = Σ unit_price × qty`.
2. `delivery_fee = fee if fulfilment == delivery else 0` (fee = per-hostel override else global).
3. `total = subtotal + delivery_fee`. **No other charges.** Prices are treated as tax-inclusive.
4. `payable = total − unique_adjust` (discount mode) / `+` (surcharge mode) / `total` (off). See 11.3.
5. Snapshot names and prices into `order_items` at order time (later menu edits never change old orders).

---

## 8. Conversation engine

### 8.1 Principles
- **Deterministic state machine.** The conversation never depends on an LLM. Templates live in `messages.yaml` (English default; add Hinglish/Bengali variants later).
- **Understand messy input, confirm before charging.** Always show a summary and get an explicit "yes/confirm/ok/haan/hoyeche" (accept a small set of affirmatives) before generating payment.
- **Few, dense messages** (message economy, C7): never send one message per question if one message can carry it.

### 8.2 States
`IDLE → COLLECTING → NEED_FULFILMENT → NEED_ADDRESS → CONFIRMING → AWAITING_PAYMENT → DONE`

Global commands (case-insensitive, punctuation-tolerant, work in any state): `menu`, `cancel`, `status`, `help`, `repeat` (re-order last), `human` (alert owner, pause bot for this customer for N minutes).

### 8.3 Flow
1. **First contact / greeting** → one message: welcome + how to order + link to menu (or short menu text) + hours.
2. **Item message** → parse (Section 9). If everything resolves: echo lines + running subtotal, then ask **in the same message**: *"Takeout or delivery (+₹15)?"* If some items are ambiguous/unknown: ask a numbered clarification for those only, keep the resolved ones.
3. **Fulfilment** → `takeout`/`pickup`/`take away`/`delivery`/`deliver`/`hostel` etc. If delivery: need `hostel` (must be in `HOSTELS`) and `room`; accept "B 204", "Hostel B room 204", saved default ("Same as last time?").
4. **Confirm** → itemised summary, delivery fee line, **Total**, and — only if unique-amount is active — the exact **Amount to pay** with a one-line explanation ("₹114.63 — small rounding so we can match your payment automatically"). Ask "Confirm?".
5. **Payment** → create payment (Section 10). Send **one** message with the pay-page link (or QR image + VPA text if no public URL), the amount, the expiry time, and: *"You'll get a confirmation here as soon as the payment reaches us. Screenshot is optional."*
6. **Paid** → "✅ Payment received. Order #A123: preparing. (Delivery ~X min / Ready in ~X min)". Owner is notified.
7. Later status pushes (`READY`, `OUT_FOR_DELIVERY`) are **optional and count toward the message budget**; default ON only for delivery orders' "out for delivery".

### 8.4 Edge cases (each needs a scenario test)
- Add/remove/change before confirming ("add 1 coke", "remove samosa", "make it 3 tea").
- Unknown or unavailable item; suggest closest (top 3) instead of failing.
- Quantity > `max_qty` → ask owner-safe question, do not silently accept.
- Special instructions ("no onion", "less spicy") → stored as line/order note, echoed in summary; never affect price.
- Ordering outside `OPEN_HOURS` → polite message; still allow browsing the menu.
- Customer sends a photo/sticker/voice/location when text expected → friendly nudge; **image after payment prompt = screenshot flow**; location during address step → store as note.
- Customer changes mind after payment prompt → `cancel` allowed while `AWAITING_PAYMENT`; after `PAID`, route to owner (`human`).
- Payment timeout → reminder at 2/3 of TTL (counts toward budget; make configurable), then `EXPIRED` with an offer to re-create.
- Blocked customer (repeated confirmed fraud flags) → silent owner alert, generic reply.
- Duplicate WhatsApp deliveries (same message id) → ignored (idempotency).
- Concurrency: two orders from one customer allowed; each has its own code and payable amount.

---

## 9. Order parser (rules-only by default)

Pipeline in `nlu/`:
1. **Normalize**: lowercase, strip emoji/punctuation, collapse spaces, transliteration-tolerant.
2. **Tokenize into segments** on `and`, `&`, `+`, `,`, `n`, newline, `aur`, `ar`, `o` (Bengali "and").
3. **Quantity extraction** per segment: digits (`2`, `2x`, `x2`, `2 pcs`, `2 plate`), number words in English/Hindi/romanized Bengali (`ek/ekta=1, do/dui/duto=2, teen/tin/tinte=3, char/charta=4, paanch/panch/pachta=5 …` — data file `nlu/numbers.yaml`, easy to extend). Default qty 1.
4. **Item resolution**: exact alias → fuzzy (`rapidfuzz.WRatio` ≥ 90 auto-accept; 75–89 ask "Did you mean …?"; < 75 unknown). Prefer longest alias; handle "chicken roll" vs "chicken egg roll" by asking when two items score within 5 points.
5. **Modifiers**: "no X", "without X", "extra X", "spicy/less spicy" → notes.
6. **Output** `ParseResult{ lines[], unresolved[], ambiguous[], notes[], confidence }`. Conversation engine decides what to ask.
7. `NLU_MODE=llm` is an **optional plug-in** that receives the same input/menu and must return the same `ParseResult` JSON (validated against schema; any item id not in menu is discarded; prices are **never** taken from the model). Ship only a stub + interface + tests with a fake client. **Not used by default.**

Acceptance: a table-driven test file with ≥ 60 realistic messages (typos, Hinglish, Bengali-romanized, mixed quantities, notes) and an accuracy floor of ≥ 95% on the provided set.

---

## 10. Collecting payment (free UPI)

### 10.1 UPI link
`upi://pay?pa=<VPA>&pn=<urlencoded PAYEE_NAME>&am=<amount 2dp>&cu=INR&tn=<Order code>`
- `am` always with exactly 2 decimals. `tn` short (≤ 40 chars): `ShopName A123`.
- Do **not** add merchant-only params (`mc`, `tid`) — this is a personal-VPA style collection. Add a config flag `UPI_INCLUDE_TR` (default off) in case some apps behave better with `tr`.
- Provide a unit test that validates URI encoding and 2-dp formatting.
- **Owner TODO:** test the link with GPay, PhonePe and Paytm on real phones; personal-VPA behaviour with pre-filled amounts can differ per app. Record results in `docs/DECISIONS.md`.

### 10.2 Pay page (`GET /pay/{token}`)
Mobile-first, no login. Shows shop name, order code, itemised lines, **big amount**, countdown, buttons: **Pay with UPI app** (`upi://` intent), **Copy UPI ID**, **Copy amount**; QR (scan from another device); **Upload screenshot** (optional; goes through the same verifier); status area that polls `GET /pay/{token}/status` every 3 s and turns into a green **"Payment confirmed ✅"** when `PAID`. Rate-limit and use unguessable 16+ char tokens; expired tokens show a friendly expired page.

### 10.3 QR image
`GET /qr/{token}.png` (also embedded in pay page). WhatsApp image message uses the public link if `PUBLIC_BASE_URL` is set, else uploads the media.

### 10.4 Expiry
Background task every 30 s: `AWAITING_PAYMENT` past `expires_at` → `EXPIRED` (release the unique amount). Credits arriving within `LATE_CREDIT_GRACE_MIN` of expiry that match an expired order → `NEEDS_OWNER` ("late payment") — never auto-resurrect silently.

---

## 11. Payment verification (the core of the product)

### 11.1 Bank-credit ingestion (`BANK_SIGNAL=sms`)

**Endpoint:** `POST /webhook/bank-sms` — auth via header `X-Webhook-Secret` **or** query `?key=` (some forwarder apps can't set headers). Constant-time compare. Accept flexible JSON keys: sender = `from|sender|address`, body = `text|message|body|content`, time = `receivedStamp|received_at|timestamp|date` (epoch ms or ISO). Respond 200 quickly; process inline (it's fast).

**Recommended free forwarder:** the open-source Android app "Incoming SMS to URL forwarder" (`bogkonstantin/android_income_sms_gateway_webhook`): forwards SMS as JSON via HTTP POST, supports sender filters/regex, retries, and an optional heartbeat. Suggested config (verify placeholder names against the app's README):
```json
{"from":"%from%","text":"%text%","sentStamp":"%sentStamp%","receivedStamp":"%receivedStamp%","sim":"%sim%"}
```
Filter to only your bank's sender ID. Disable battery optimisation for the app. Note the app forwards **SMS only** (not RCS).
Document in `docs/SMS_FORMATS.md` and the runbook. Alternatives (write as notes only): a Termux script, a bank's email alerts, or **manual paste** in the console.

**Manual fallbacks (must exist, they double as the demo tools):**
- Console → *Paste bank SMS* box → same parser.
- Console → *Add credit manually* (amount, UTR optional, time).
- Simulator → *Simulate bank credit for order X* (uses the order's exact payable amount + random UTR).

**Fail-safe:** if the forwarder is down, nothing is ever falsely marked paid; payments simply escalate to owner review. Track `last_credit_seen_at` and (if the app's heartbeat is used) `last_heartbeat_at`; during `OPEN_HOURS`, alert the owner if no heartbeat for 30 min.

### 11.2 SMS parser (`verify/sms_parsers`)

Steps, each individually unit-tested:
1. **Sender filter** with `BANK_SMS_SENDERS`; non-matching → stored as `ignored`.
2. **Noise filter**: contains `OTP`, "do not share", offer/loan/promo language → `ignored`.
3. **Direction**: credit words (`credited`, `received`, `deposited`, `CR`) vs debit words (`debited`, `sent`, `paid`, `withdrawn`, `DR`). **Debits are stored and never matched.**
4. **Amount**: `(?:Rs\.?|INR|₹)\s?([\d,]+(?:\.\d{1,2})?)` → paise.
5. **UTR**: labelled patterns (`UPI Ref`, `UPI Txn`, `UTR`, `RRN`, `Ref No`) followed by a 12-digit number; fallback: a standalone 12-digit number.
6. **Payer hint**: any `name@handle` VPA or "from/by NAME" fragment (optional, never used for matching decisions).
7. **Time**: parse from text if present, else `received_at`.
8. **Dedupe**: same `utr`, or same `raw_hash` — forwarders retry, so this must be idempotent.
9. **Redact**: store masked text only (strip account/card digits beyond last 4).
10. **Plug-in registry**: `banks/<bank>.py` files register a sender regex + specific regexes and override `generic`. Ship `generic.py` + 4 synthetic bank-style examples (Appendix D). Provide `python -m shopbot.tools.test_sms "<pasted sms>"` that prints the parse result and which parser fired — the owner uses this to check their own bank's format and reports failures.

### 11.3 Unique amount (makes matching unambiguous, at ~₹0 cost)

Many orders have identical totals (e.g., ₹60). To match a credit to exactly one order, give each *pending* order a **distinct payable amount** by shifting it by 1–`UNIQUE_PAISE_MAX` paise:

- `discount` (default): `payable = total − k paise`. The owner absorbs ≤ ₹0.30, average ≈ ₹0.15. Customers never pay more. **This is the default because the owner does not want to raise charges.**
- `surcharge`: `payable = total + k`. Available but **not** default.
- `off`: `payable = total`; matching relies on time window + UTR + owner review; collisions are routed to owner.
- Allocation: pick the smallest unused `k` among orders currently `AWAITING_PAYMENT`/`PENDING_BANK`/within grace with the same base total; if exhausted, widen the range by 10 or fall back to `off` for that order (and flag it).
- Show the exact payable amount to the customer with a one-line reason. Amounts with paise are fully supported by UPI apps.
- Owner can change mode in `.env`; document the trade-off in README.

### 11.4 Matching engine (`verify/matcher.py`)

Run **every time** a credit is stored and **every time** an order/screenshot state changes; wrap in a DB transaction.

```
on_new_credit(c):
  if c.direction != credit: return
  candidates = orders where payment_state in (NONE,CLAIMED,PENDING_BANK,NEEDS_OWNER)
               and status in (AWAITING_PAYMENT, EXPIRED-within-grace)
               and payable_paise == c.amount_paise      # exact (or within AUTO_ACCEPT_OVERPAY_PAISE, overpay only)
               and order.created_at <= c.txn_time <= order.expires_at + grace
  if screenshot for some order carries utr == c.utr: prefer that order
  if len(candidates) == 1: mark PAID (paid_via='bank_sms', method='amount_unique'|'utr'), notify customer + owner
  elif len(candidates) > 1: NEEDS_OWNER (ambiguous; show candidates)
  else: keep credit UNMATCHED; if a near-miss order exists (same customer's pending order, amount differs) → NEEDS_OWNER with reason "wrong amount: paid X, expected Y"

on_new_screenshot_report(order, report):
  if report.utr and credit = credits.by_utr(report.utr):
      if credit.status == MATCHED to another order: flag DUPLICATE_UTR (fraud signal) → owner alert
      elif credit.amount_paise == order.payable_paise: mark PAID (method='utr')
      else: NEEDS_OWNER "amount mismatch: bank shows X, expected Y"
  else: apply verdict table (11.5)
```

Idempotent: a credit can match at most one order; an order at most one credit (unique constraints).

### 11.5 Screenshot verifier (`verify/screenshot`)

**Pipeline** `verify_screenshot(order, image_bytes) -> ScreenshotReport`:

1. **Validate file**: is an image, ≤ 8 MB, ≥ 300 px on the short side; decode safely with Pillow; downscale to ≤ 2000 px; strip nothing from the stored original. Non-image (PDF/video) → ask for a screenshot image.
2. **Fingerprints**: `sha256`, perceptual hash (`imagehash.phash`). Same sha256 or pHash Hamming ≤ 4 seen on *another* order → `DUPLICATE_IMAGE` (hard fail).
3. **OCR** via `OcrEngine` → lines with confidence. Mean confidence < 0.5 or almost no text → `UNREADABLE` → ask for a clearer screenshot (max 2 retries, then owner).
4. **Extract** (best effort, tolerant to OCR noise — e.g. `₹` misread as `T`, `2`, `%`, `Z`):
   - `app`: GPay / PhonePe / Paytm / BHIM / other (keyword sniffing).
   - `status`: success words (`paid`, `payment successful`, `completed`, `success`) vs failure/pending words (`failed`, `pending`, `processing`, `declined`, `cancelled`, `reversed`).
   - `amount`: **expected-value check first** — does the expected payable (`114.63`, also `114.63` inside `₹1,114.63` must NOT count) appear as a whole numeric token? Then a generic amount candidate list for mismatch reporting.
   - `utr`: labelled 12-digit (`UPI transaction ID`, `UTR`, `UPI Ref No`); fallback: any standalone 12-digit number; also capture app-specific transaction IDs (e.g. PhonePe `T…`) into `app_txn_id` (not used for bank lookups).
   - `payee`: name and/or VPA text.
   - `datetime`: many formats (`20 Sep 2026, 3:45 pm`, `Sep 20, 2026 15:45`, `20/09/2026`), parsed as IST.
5. **Checks** (each `PASS | FAIL | UNKNOWN` + reason):

| ID | Check | Hard fail? |
|---|---|---|
| C1 | Looks like a UPI payment screen | yes |
| C2 | Status is success (no failure/pending words) | yes |
| C3 | Expected payable amount present exactly; different amount only ⇒ FAIL | yes |
| C4 | Payee matches `PAYEE_NAME`/aliases (fuzzy ≥ 85) or VPA handle matches | yes (if payee text found) |
| C5 | Timestamp within `[order.created_at − 2 min, now + 5 min]` | yes if parsed & outside |
| C6 | UTR present (12 digits) | soft |
| C7 | UTR not already used by another order/credit | yes |
| C8 | Image not a duplicate | yes |
| C9 | Metadata advisory: EXIF `Software` shows an image editor (Photoshop/Canva/Snapseed/PicsArt…), implausible aspect ratio | soft (advisory only) |

   Note for C9: WhatsApp strips most metadata from normally-sent photos, so this is weak; keep it advisory and say so in docs.
6. **Bank cross-check** (decisive): by UTR if extracted, else by exact amount in time window (works well when unique-amount is on). Outcomes: `BANK_CONFIRMED`, `BANK_MISMATCH` (credit found but amount/order differs), `BANK_PENDING` (nothing yet).

**Verdict table (order of evaluation):**

| Situation | Verdict | Effect |
|---|---|---|
| Credit already matched to this order (any path) | `PAID` | Screenshot ignored/used for reinforcement. Reply "already confirmed ✅". |
| `BANK_CONFIRMED` | `PAID` | `paid_via='bank_sms'`. |
| `BANK_MISMATCH` | `NEEDS_OWNER` | Show bank amount vs expected; owner decides (accept/top-up/refund). |
| Any **hard fail** and no bank confirmation | `REJECTED_CLAIM` | Neutral message to customer: "We couldn't verify this — please pay the exact amount using the link (or send a clearer screenshot)". Owner alerted with the failed checks; C7/C8 increments `fraud_flags`. Never accuse. |
| No hard fails, `BANK_PENDING`, `BANK_SIGNAL=sms` | `PENDING_BANK` | "Got it — waiting for bank confirmation (usually under a minute)". Re-run matcher on each new credit; after `PENDING_BANK_TIMEOUT_MIN` → `NEEDS_OWNER`. |
| No hard fails, `BANK_SIGNAL=none` | `NEEDS_OWNER` | Owner sees screenshot + extracted UTR/amount + "check this UTR in your bank app" + Approve/Reject. |
| `SCREENSHOT_POLICY=auto_approve_if_strong` (**off by default, warn loudly in README**) | `PAID_UNVERIFIED` | Only if: C1–C8 all PASS incl. UTR present, order ≤ `AUTO_APPROVE_MAX_PAISE` (default ₹150), customer has ≤ 1 unverified order/day and no fraud flags. Order is flagged **"UNVERIFIED — reconcile with bank"** on the console and re-checked when a credit later arrives or when the day ends. |

**Owner assist.** The review card must show: the screenshot, extracted fields with per-check ✓/✗, the expected amount/UTR to look for, and one-tap **Approve (I saw the credit)** / **Reject**. Every approve/reject is audit-logged with the owner's note.

### 11.6 Payment state machine

```
AWAITING_PAYMENT ──credit matched──────────────▶ PAID
      │  └─screenshot ok─▶ PENDING_BANK ─credit matched─▶ PAID
      │                       └─timeout─▶ NEEDS_OWNER ─approve─▶ PAID (paid_via='owner')
      │                                       └─reject──▶ AWAITING_PAYMENT | CANCELLED
      ├─hard-fail screenshot─▶ REJECTED_CLAIM ─customer pays properly─▶ (credit match) PAID
      ├─TTL─▶ EXPIRED ──late credit──▶ NEEDS_OWNER (late payment)
      └─customer/owner cancel─▶ CANCELLED (if already PAID → "refund needed" flag for the owner)
```
Illegal transitions raise errors and are covered by tests.

### 11.7 Abuse / failure matrix (each row = a scenario test)

| Scenario | Detection | Outcome |
|---|---|---|
| Fake/edited screenshot, no real payment | No credit ever arrives; maybe C3/C4/C5 fail | Never `PAID`; owner alerted at timeout |
| Paid ₹1, edited screenshot to show full amount | Credit found by UTR with different amount | `NEEDS_OWNER: amount mismatch` |
| Same screenshot reused on a new order | sha256/pHash + UTR already matched | `REJECTED_CLAIM`, fraud flag |
| Real old screenshot of another payment | C5 fails, UTR already used | `REJECTED_CLAIM` |
| Screenshot shows different payee | C4 fails | `REJECTED_CLAIM` |
| "Payment pending/failed" screenshot | C2 fails | Ask to retry after payment completes |
| Paid exact amount, never sent screenshot | Credit matches by unique amount | Auto `PAID` (screenshot is optional) |
| Two pending orders same total, unique-amount off | Multiple candidates | `NEEDS_OWNER` with both listed |
| Wrong amount (underpaid/overpaid) | No exact match; near-miss | `NEEDS_OWNER` with difference |
| Payment after expiry | Credit within grace | `NEEDS_OWNER (late)` |
| Friend pays from another phone | Payer name is **not** checked | Works normally |
| Forwarder duplicated/retried SMS | `utr`/`raw_hash` unique | Idempotent |
| Debit/OTP/promo SMS | Direction/noise filters | Ignored |
| Forwarder phone offline | No credits; heartbeat alarm | Everything goes to owner; nothing falsely `PAID` |
| Customer sends selfie/random image | C1 fails | Polite nudge |
| Credit unrelated to any order (owner's personal income) | No candidates | Sits in "Unmatched credits" (owner can dismiss) |
| Payment later reversed by the bank | Owner marks credit `REVERSED` | Order flagged, owner alerted |

---

## 12. Owner console & notifications

Web app at `/admin` (password from `ADMIN_PASSWORD`, signed session cookie, CSRF on POST, binds to `127.0.0.1` unless `BIND_HOST` says otherwise). **Mobile-friendly** (the owner will use a phone on the shop Wi-Fi/tunnel). Auto-refresh via polling/htmx; optional browser beep on new paid order.

Pages:
1. **Live board**: columns `Paid → Preparing → Ready → Out for delivery → Done`, each card with items, notes, hostel/room, customer number, amount, one-tap status buttons. Print-friendly **kitchen slip** per order.
2. **Needs attention**: `NEEDS_OWNER` items (screenshot preview + check results + Approve/Reject), late payments, ambiguous matches, fraud alerts.
3. **Bank credits**: recent credits, unmatched ones, *Paste SMS*, *Add credit manually*, dismiss/mark reversed; "forwarder health" (last credit/heartbeat time).
4. **Menu**: toggle availability, edit price/aliases, add item; export to YAML.
5. **Customers**: history, blocked flag, fraud flags.
6. **Reports**: today/week sales, order count, delivery vs takeout, unverified-payment list, **CSV export** (for bookkeeping), outbound-message counter vs `MESSAGE_FREE_ALLOWANCE` (warn at 80%).
7. **Simulator** (`/sim`, only when `CHANNEL=simulator` or `DEBUG`): see 13.1.

**Owner notifications** (`OWNER_NOTIFY`): `console` (log + dashboard) or `telegram` (free Bot API via plain `httpx`; no library). Events: new paid order, needs-owner item, suspected fraud, unmatched credit, forwarder silent, message allowance ≥ 80%. Each notification links to the console page.

---

## 13. Channels

### 13.1 Simulator (Phase 1; the demo works with **zero** accounts)
`/sim`: a WhatsApp-like chat UI with a customer switcher, image attach (to simulate a screenshot), a **"Bank SMS injector"** (paste text or "simulate exact payment for order X / wrong amount / duplicate"), a **time-warp** control (skip N minutes to test expiry/reminders), and a live view of what the owner would see. All scenario tests drive the engine through the same `Channel` interface, so the simulator and WhatsApp behave identically.

### 13.2 WhatsApp Cloud API adapter (Phase 5)
Official Cloud API only (constraint C8).
- **Webhook verify** `GET /webhook/whatsapp`: echo `hub.challenge` when `hub.verify_token` matches.
- **Webhook receive** `POST /webhook/whatsapp`: validate `X-Hub-Signature-256` (HMAC-SHA256 of the raw body with the app secret; constant-time compare); return 200 immediately and process in a background task; **idempotent on `messages[].id`**; ignore `statuses` payloads (log delivery errors).
- **Inbound types**: `text`, `image` (screenshot), `interactive`/`button` replies; others → friendly nudge.
- **Media download**: two-step (media id → temporary URL → download with bearer token); validate size/type; store under `media/` with hashed names.
- **Outbound**: text; image (public link if `PUBLIC_BASE_URL`, else upload media); optional interactive buttons for takeout/delivery/confirm (fallback to text if not available).
- Graph API version is an env var (see Section 5) — look up a currently supported version at build time.
- Retries with backoff on 429/5xx; never block the webhook response.
- **Test setup (owner steps, put in `docs/GO_LIVE.md`)**: create a Meta developer app → add WhatsApp → note the auto-created **test number** and **Phone Number ID** → add up to **5** recipient numbers (each confirms via a code) → create a token (the quick-start token is temporary; create a system-user token for a long-lived one) → set the webhook callback URL (`PUBLIC_BASE_URL/webhook/whatsapp`) + verify token → subscribe to the `messages` field. Free tunnel URL changes on restart ⇒ re-paste the callback URL each time (or use a stable free option from `docs/DEPLOY_FREE.md`).
- **Production checklist** (`docs/GO_LIVE.md`): dedicated business number (ask the BSP/Meta docs about options if the number is currently on the regular WhatsApp app), Meta business verification as required, display name approval, payment method on file with Meta, re-check current pricing, opt-in wording, privacy notice line ("We store your order and payment screenshot to confirm payment; deleted after N days").

### 13.3 Message economy (constraint C7)
Target ≤ 7 outbound messages per order: welcome/summary (1), clarifications (0–2), confirm (1), pay link (1), paid (1), out-for-delivery (0–1), reminder (0–1). Log every outbound message in `outbound_log`; console shows month-to-date count vs allowance. Provide a config to disable optional status pushes. Never send the same info twice.

### 13.4 Optional Phase 6: web order page (`/order`)
Mobile page where the customer taps items, picks takeout/delivery (+₹15), enters hostel/room, and lands on the pay page. Uses the same engine and pricing; reduces WhatsApp messages to ~2 per order and eliminates parsing errors. The chat bot then only sends the link and the "paid" confirmation.

---

## 14. Security & privacy

- Secrets only via `.env` (git-ignored); startup fails loudly if required secrets are missing or left at placeholders.
- Verify WhatsApp signatures; shared-secret + constant-time compare on SMS endpoint; optional IP allow-list for the SMS endpoint.
- Console auth, CSRF, secure cookies when HTTPS, login rate limit.
- File uploads: content-type sniffing, size limits, Pillow decode in try/except, randomised filenames, no path traversal.
- Never log tokens, full SMS bodies, or full phone numbers (mask middle digits).
- Store only what's needed: masked SMS text, parsed fields, order data. Purge stored screenshot files after `MEDIA_RETENTION_DAYS` (keep hashes for duplicate detection). Provide `python -m shopbot.tools.purge`.
- Nightly local backup of the SQLite file (`backups/`, keep 14); document how to copy it to a USB/Drive by hand.
- SQL via ORM/parameters only. Pin dependency versions; note `pip-audit`/`pip list --outdated` in README.

---

## 15. Testing

### 15.1 Unit
Money/paise math; pricing; unique-amount allocation & release; UPI URI building; number-word parsing; fuzzy resolution; SMS parser (credit/debit/OTP/promo, dedupe, redaction); matcher (single/ambiguous/none/near-miss/late); state-machine legality; webhook signature validation; config validation.

### 15.2 Scenario (end to end through the Channel interface)
At least these, each asserting DB state **and** messages sent:
1. Happy path takeout, SMS credit arrives, no screenshot → auto `PAID`.
2. Happy path delivery (+₹15), screenshot first then SMS → `PENDING_BANK → PAID`.
3. Screenshot only, no SMS ever → `NEEDS_OWNER` at timeout; owner approves → `PAID(owner)`.
4. Fake screenshot (wrong amount / wrong payee / old date / failed status / duplicate UTR / duplicate image) each → `REJECTED_CLAIM`, never `PAID`.
5. Underpay and overpay → `NEEDS_OWNER` with difference.
6. Expiry → `EXPIRED`; late credit → `NEEDS_OWNER (late)`.
7. Two simultaneous orders with same base total → different payable amounts → each credit matches its own order.
8. Forwarder retry duplicates → single credit.
9. Ambiguous/unknown items, add/remove, notes, out-of-hours, blocked customer, duplicate WhatsApp message id.
10. `BANK_SIGNAL=none` → all payments owner-confirmed.

### 15.3 Synthetic screenshots
`tools/make_fake_screenshot.py` renders GPay/PhonePe/Paytm-*style* confirmation images with Pillow (parameters: amount, UTR, payee, datetime, status, app). Used for pass/fail OCR tests. `FakeOcrEngine` reads a sidecar JSON so CI doesn't depend on OCR quality; a separate marked test (`-m ocr`) runs the real engine on the synthetic images.

### 15.4 Real-world evaluation (owner-run, required before trusting OCR)
`python -m shopbot.tools.eval_screenshots <folder>` runs the pipeline on ~20 real, redacted screenshots (with an optional `labels.csv`: expected amount/UTR/status) and prints per-field accuracy + failures. Target ≥ 90% on amount, UTR and status; if lower, tune extraction regexes/preprocessing (grayscale, contrast, upscale) and record results in `docs/DECISIONS.md`.

### 15.5 Quality gates
`ruff` clean; `pytest` green; ≥ 85% coverage on `payments/`, `verify/`, `menu/`, `nlu/`.

---

## 16. Build phases and acceptance criteria

| Phase | Deliverable | Acceptance |
|---|---|---|
| **0 Scaffold** | Repo, config, DB models, logging, CI-style `make test`, `README` skeleton | `python -m shopbot --help` works; tests run |
| **1 Core + Simulator** | Menu, pricing, parser, conversation, orders, UPI link/QR, **pay page**, `/sim` chat UI, expiry job | Demo: type an order in `/sim`, reach payment prompt with correct total (+₹15 for delivery) |
| **2 Bank verification** | Credits ingestion endpoint, SMS parsers + CLI, matcher, unique amounts, SMS injector in `/sim` | Scenarios 1, 2(SMS part), 7, 8 pass; pay page flips to "confirmed ✅" |
| **3 Screenshot verifier** | Full pipeline, checks, verdict table, synthetic generator, eval tool | Scenarios 3, 4, 5, 6 pass; OCR test on synthetic images ≥ 95% on amount/UTR |
| **4 Owner console** | Board, needs-attention, credits, menu, reports/CSV, Telegram notifier | Owner can run a full day in the console on a phone browser |
| **5 WhatsApp adapter** | Cloud API webhook/send/media, signature check, idempotency, message counter | Works end-to-end with the free test number and ≤ 5 recipients |
| **6 Hardening (+ optional `/order` page)** | Rate limits, backups, purge, health checks, docs, go-live checklist | `docs/GO_LIVE.md` complete; soak test of 200 simulated orders with no false `PAID` |

`python -m shopbot.tools.seed_demo` + `python -m shopbot demo` must replay a scripted day (10 orders incl. fraud cases) and print a pass/fail summary.

---

## 17. Owner runbook (write into `README.md` in plain English)

1. Install Python 3.11+ → `python -m venv .venv` → activate → `pip install -e .` (or `run.bat`/`run.sh` doing this).
2. Copy `.env.example` → `.env`; set `UPI_VPA`, `PAYEE_NAME`, `SMS_WEBHOOK_SECRET`, `ADMIN_PASSWORD`. Edit `menu.yaml`.
3. `python -m shopbot run` → open `http://127.0.0.1:8000/sim` (demo) and `/admin`.
4. **Bank SMS forwarding:** install the SMS-forwarder app on the phone that receives your bank credit alerts; point it to `http://<PC-LAN-IP>:8000/webhook/bank-sms?key=<SMS_WEBHOOK_SECRET>` (same Wi-Fi; requires `BIND_HOST=0.0.0.0`) or the tunnel URL; filter to your bank's sender; paste 5–10 real credit SMS (redacted) into `python -m shopbot.tools.test_sms` and fix any that don't parse.
5. **Public URL (needed for pay page links and WhatsApp webhook):** follow `docs/DEPLOY_FREE.md`.
6. **WhatsApp test number:** follow `docs/GO_LIVE.md` (max 5 recipients).
7. Run `eval_screenshots` on real screenshots. Do not enable `auto_approve_if_strong` unless the results are good **and** you accept the risk.

---

## 18. Out of scope now / upgrade path

- Payment-gateway adapter (Razorpay etc.): interface `PaymentVerifier` already isolates "how do we learn money arrived"; a gateway webhook adapter can replace SMS ingestion later (costs/KYC).
- LLM order parser (`NLU_MODE=llm`), voice notes, multilingual replies beyond templates, loyalty/discounts, cash-on-delivery, multi-shop, inventory counts, riders' app, Google-Sheets sync, CSV bank-statement reconcile.
- Anything that needs unofficial WhatsApp automation.

---

## 19. Definition of done

- [ ] `python -m shopbot demo` passes on a clean machine (Windows + Linux) with no external accounts.
- [ ] All scenario tests in 15.2 pass; `ruff` clean; coverage target met.
- [ ] No code path marks `PAID` except a matched credit or an audited owner action (or the explicit `auto_approve_if_strong` policy, which is off by default). Add a test that greps/asserts this invariant.
- [ ] Default config makes **no** paid or external calls.
- [ ] Unique-amount default is `discount`; no customer-facing charge is ever above `total`.
- [ ] `README.md`, `docs/OWNER_TODO.md`, `docs/SMS_FORMATS.md`, `docs/DEPLOY_FREE.md`, `docs/GO_LIVE.md` written; placeholders clearly listed.
- [ ] Every deviation from this spec recorded in `docs/DECISIONS.md`.

---

## Appendix A — Dummy menu (replace with real)

| Item | ₹ | Aliases |
|---|---|---|
| Tea | 10 | chai, cha |
| Coffee | 15 | coffee, kofi |
| Samosa | 10 | samosa, singara |
| Veg Roll | 40 | veg roll |
| Egg Roll | 50 | egg roll, e roll |
| Chicken Roll | 70 | chicken roll, chkn roll |
| Maggi | 35 | maggi, noodles |
| Egg Maggi | 45 | egg maggi |
| Veg Fried Rice | 80 | veg rice, veg fried rice |
| Chicken Fried Rice | 110 | chicken rice |
| Cold Drink | 20 | coke, pepsi, cold drink |

## Appendix B — Example UPI link
`upi://pay?pa=shopname@bank&pn=Shop%20Owner&am=114.63&cu=INR&tn=ShopBot%20A123`

## Appendix C — Message templates (`messages.yaml`, sample)
- `welcome`: "Hi! 👋 Welcome to {shop}. Send your order like *2 samosa, 1 chai*. Takeout or hostel delivery (+₹{fee}). Open {hours}."
- `summary`: "{lines}\nSubtotal ₹{subtotal}\nDelivery ₹{fee}\n*Total ₹{total}*{unique_note}\nConfirm? (yes/no)"
- `pay`: "Pay ₹{payable} here 👉 {pay_url}\n(valid till {expires}). You'll get a confirmation here as soon as it reaches us — screenshot is optional."
- `paid`: "✅ Payment received for order {code}. {eta}"
- `claim_pending`: "Thanks! Waiting for the bank to confirm — usually under a minute."
- `claim_rejected`: "We couldn't verify that screenshot. Please pay the exact amount using the link, or send a clearer screenshot."
- `expired`: "Order {code} expired. Reply *repeat* to place it again."

## Appendix D — Synthetic bank SMS fixtures (ILLUSTRATIVE ONLY; the owner must replace with real redacted samples)
```
# credit, style 1
Rs 114.63 credited to A/c XXXXXX1234 on 20-09-26 by UPI Ref No 123456789012. -DEMO BANK
# credit, style 2
Your a/c XX1234 is credited with INR 60.00 on 20/09/2026 from rahul@okaxis (UPI Ref 210987654321). Avl bal INR 5,431.20
# credit, style 3
UPI/CR/345678901234/RAHUL K/DEMO/20-09-2026 Rs.85.40 credited to XX1234
# credit, style 4
Dear Customer, INR 45.50 received in your account XXXX1234 via UPI on 20-Sep-26. UTR: 456789012345
# debit (must be ignored)
Rs 500.00 debited from A/c XXXXXX1234 on 20-09-26 UPI Ref No 999999999999.
# OTP (must be ignored)
123456 is your OTP for login. Do not share with anyone.
```

## Appendix E — Bank-SMS endpoint contract
`POST /webhook/bank-sms?key=<secret>` (or header `X-Webhook-Secret`)
```json
{"from":"VM-DEMOBK","text":"Rs 114.63 credited to A/c XXXXXX1234 ... UPI Ref No 123456789012","receivedStamp":"1789900000000","sim":"sim1"}
```
Response: `200 {"status":"stored|duplicate|ignored","matched_order":"A123|null"}`.

## Appendix F — Screenshot report (JSON shape)
```json
{
  "order": "A123", "expected_payable": "114.63",
  "ocr_confidence": 0.87,
  "extracted": {"app":"gpay","status":"success","amount":"114.63","utr":"123456789012","payee":"SHOP OWNER NAME","datetime":"2026-09-20T15:45:00+05:30"},
  "checks": {"C1":"PASS","C2":"PASS","C3":"PASS","C4":"PASS","C5":"PASS","C6":"PASS","C7":"PASS","C8":"PASS","C9":"UNKNOWN"},
  "bank_cross_check": "BANK_PENDING",
  "verdict": "PENDING_BANK",
  "reasons": []
}
```

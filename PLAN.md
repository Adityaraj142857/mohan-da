# PLAN.md — ShopBot build plan

Tracking implementation of `flow/SPEC.md` against `flow/PROBLEM_STATEMENT.md`.
Scope note: this build targets phases 0-4 fully (scaffold, core engine +
simulator, bank verification, screenshot verification, owner console) plus a
channel-agnostic WhatsApp Cloud API adapter skeleton (phase 5) that is
correct but cannot be *live-tested* without a real Meta account. Hardening
extras (phase 6) are covered where cheap (purge tool, backups helper) and
otherwise documented as owner follow-ups in `docs/OWNER_TODO.md`.

## Phase 0 — Scaffold
- [x] Repo layout per SPEC 4.2
- [x] `pyproject.toml` deps, `src` layout, entry point `python -m shopbot`
- [x] `config.py` (pydantic-settings), `db.py`, `models.py`, `money.py`, `clock.py`
- [x] `.env.example`, `menu.yaml`, `messages.yaml`
- [x] `pytest` wired, `make test` via `scripts/`

## Phase 1 — Core + Simulator
- [x] `menu/loader.py`, `menu/pricing.py` (pure, unit-tested)
- [x] `nlu/normalizer.py`, `nlu/parser.py`, `nlu/numbers.yaml`
- [x] `conversation/engine.py`, `states.py`, `templates.py`
- [x] `orders/service.py`, `codes.py`
- [x] `payments/upi.py`, `qr.py`, `paypage.py`, `expiry.py`
- [x] `channels/base.py`, `channels/simulator.py`
- [x] `/sim` UI + pay page + `/pay/{token}` + `/pay/{token}/status`

## Phase 2 — Bank verification
- [x] `verify/sms_parsers/generic.py` + 4 bank-style plug-ins
- [x] `POST /webhook/bank-sms`, `tools/test_sms.py`
- [x] `verify/matcher.py`, `payments/unique_amount.py`
- [x] SMS injector in `/sim`

## Phase 3 — Screenshot verifier
- [x] `verify/screenshot/{extract,checks,forensics,pipeline}.py`
- [x] `OcrEngine` interface + `FakeOcrEngine` (+ optional RapidOCR/Tesseract engines)
- [x] `tools/make_fake_screenshot.py`, `tools/eval_screenshots.py`

## Phase 4 — Owner console
- [x] `admin/routes.py` + templates: board, needs-attention, credits, menu, customers, reports, sim
- [x] `notify/console.py`, `notify/telegram.py`

## Phase 5 — WhatsApp adapter (skeleton, off by default)
- [x] `channels/whatsapp_cloud.py`, webhook verify/receive, signature check, idempotency
- [x] `docs/GO_LIVE.md`

## Phase 6 — Hardening (partial)
- [x] `tools/purge.py` for media retention
- [x] `docs/DEPLOY_FREE.md`, `docs/SMS_FORMATS.md`, `docs/OWNER_TODO.md`, `docs/DECISIONS.md`
- [ ] Full 200-order soak test (left as owner exercise; `tools/seed_demo.py` covers a scripted day)

## Tests
- Unit: money, pricing, unique-amount, UPI URI, number-words, fuzzy resolution, SMS parsing, matcher, state machine, webhook signature, config validation, analytics (sales, products, inventory, customers, recommendations).
- Scenario (via simulator channel): happy path takeout/delivery, screenshot+SMS ordering, screenshot-only + owner approve, fake screenshot variants, under/overpay, expiry + late credit, concurrent same-total orders, forwarder retry dedupe, BANK_SIGNAL=none.

## Phase 7 — Business Operations Platform (Extension)
- [x] `models.py` extension: `Inventory`, `Promotion`, `Order.inventory_deducted`
- [x] `analytics/` service package (pure aggregation, no external API dependency)
- [x] Owner Dashboard (`/admin`), moving Kanban to `/admin/board`
- [x] Sub-pages: Inventory, Recommendations, Daily Summary, Customer Detail
- [x] Idempotent inventory deduction hook on `mark_paid`
- [x] 11 deterministic analytics unit tests (total test suite 141)
- [x] `python -m shopbot seed-demo-analytics` tool

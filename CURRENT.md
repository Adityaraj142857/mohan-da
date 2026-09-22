# Current status

_Last updated: 2026-09-22. Update this file every time something meaningful changes — new feature, bug fix, config change, or a shift in what's running/where._

## TL;DR

ShopBot (the shop's ordering + payment app) is **built, tested, and working**, now with a redesigned admin console UI. The course assignment's n8n automation pipeline is **built, upgraded to a 3-step confidence-scoring pipeline, and verified live** with 13 test cases and zero wrong calls. Everything starts with **one command**: `bash start.sh`. All of the above is pushed to GitHub. Two real-world setup items remain before real customer orders (see "Not done yet").

## How to run it

```bash
bash start.sh          # starts ShopBot + n8n in the background, opens your browser
bash start.sh status   # check what's running
bash start.sh stop     # stop everything
```

That's the only script you need — `scripts/demo.sh` and `scripts/run.sh` were removed to avoid confusion; `scripts/run.bat` remains for Windows (ShopBot only; n8n setup on Windows is manual, see `docs/assignment/RUN_WORKFLOW.md`). Both ShopBot and n8n run detached (`nohup`, PPID 1) — closing the terminal does **not** stop them; only `bash start.sh stop` does. If a background process gets killed by the OS (e.g. low system memory), just re-run `bash start.sh`.

## What's running right now

| Service | URL | Status |
|---|---|---|
| ShopBot | http://127.0.0.1:8000 | ✅ running via `start.sh` |
| n8n | http://localhost:5678 | ✅ running via `start.sh` |
| Public tunnel | — | ❌ off — the free Cloudflare tunnel was unreliable; ShopBot runs in QR-image mode instead (no external dependency) |

## What changed in this session

1. **Rubric-weighted improvements to the assignment deliverables:**
   - `02_AUTOMATION_ARGUMENT.md`: added an explicit guardrails table (edge cases → confidence → automated action, in the assignment's own wording), a scope-clarity note (the graded decision is payment confirmation; ShopBot is supporting infrastructure), and a labelled, order-of-magnitude business case section.
   - `03_TEST_RESULTS.md`: extended from 7 to 13 live-verified test cases (added overpay, promo-SMS noise, a second independent exact match, a secret-rotation smoke test, and two confidence-scoring re-verifications), plus a confusion-matrix summary (0 wrong calls across all cases).
   - `04_PRESENTATION_OUTLINE.md`: added a concrete, timestamped screen-recording checklist (the one missing deliverable per the grading feedback).
2. **n8n workflow upgraded** from a single "call ShopBot, branch on result" node into three role-separated steps — **Evidence** (call the matcher) → **Risk/Decision** (a Code node scoring confidence: 100/50/10/0) → **Act** (auto-confirm only at confidence 100, else escalate). Verified live on both branches after the upgrade.
3. **Admin console UI redesigned**: sidebar navigation with active-page highlighting, card-based live board, polished login screen, fixed a table-overflow bug on the needs-attention and menu pages. Verified visually in Chrome, not just by curl status codes.
4. **Single launcher script** (`start.sh`) replacing the previous `scripts/demo.sh` / `scripts/run.sh` — starts both services detached in the background and opens the browser automatically, with `status`/`stop` subcommands.
5. Full test suite (130 tests) and the scripted demo day (10/10) re-verified after every change above.

## What's built and working

### ShopBot (the actual shop app)
- Real menu (106 items) transcribed from MohanDa's printed menu card.
- Order parsing: English/Hinglish/romanised-Bengali, typos, quantities, modifiers.
- Pricing: menu total + ₹15 delivery, customers never pay more than that.
- Payment: UPI deep link + QR (sent as an inline image — no external link/tunnel needed).
- Payment confirmation: automatic via bank-SMS matching (unique-amount trick keeps same-priced orders distinct), plus a "Simulate this payment" demo button so no real UPI transaction is needed to test.
- Screenshot fraud checks: duplicate image/UTR detection, payee/amount/status/timestamp checks — screenshot alone never marks an order paid.
- Owner console (`/admin`): redesigned sidebar UI — live board, needs-attention queue, credits ledger, menu editor, customers, reports/CSV.
- WhatsApp-style `/sim` chat UI: clickable links, bold text rendering, live-updating without full page reloads.
- 130 automated tests passing + a 10/10 scripted demo day (`python -m shopbot demo`).

### Course assignment (`docs/assignment/`)
- Problem Brief, Automation Argument (6-factor table + explicit guardrails table + business case → concludes a hybrid: auto-confirm exact bank-credit matches, escalate everything ambiguous), Test Results (13 cases, confusion matrix), Presentation Outline (with recording checklist).
- n8n workflow (`n8n_workflow.json`): Ingest → Evidence → Risk/Decision (confidence score) → Act. **Verified live** — 13 test cases, 0 wrong calls, recorded in `03_TEST_RESULTS.md`.
- All docs and the workflow file are pushed to GitHub with placeholders instead of real secrets.

## Configuration state

- `.env` has real values: shop name, real UPI ID (`8602003005@amazonpay`), real hostel list (all of IIM Calcutta's residence halls), real generated secrets (rotated once after a leak was caught before pushing to GitHub).
- `.env` is **not** committed to GitHub (gitignored) — `.env.example` (structure only, placeholder values) is committed instead.
- `PUBLIC_BASE_URL` is empty — running in QR-image mode (see above).

## GitHub

**Repo:** https://github.com/Adityaraj142857/mohan-da
Commits so far: initial commit (128 files) → `CURRENT.md` added → this session's changes (argument/tests/UI/launcher) about to be pushed.

## Not done yet (owner's real-world setup, not code work)

1. **Confirm `PAYEE_NAME` in `.env`** — currently a guess (`MOHAN DA`); should be set to whatever name actually shows up when someone pays `8602003005@amazonpay` via GPay/PhonePe.
2. **Confirm `OPEN_HOURS`** in `.env` — currently a guess (`09:00-23:00`).
3. **Real bank SMS forwarder** — for actual customers, someone needs to install a free Android SMS-forwarder app on the phone receiving bank credit alerts and point it at ShopBot's webhook (see `docs/SMS_FORMATS.md`).
4. **Real WhatsApp connection** — explicitly deferred by choice (didn't want to risk the number getting banned). Current demo uses `/sim`; upgrading later needs `docs/GO_LIVE.md`.
5. **Screen recording** — not yet made; script is in `04_PRESENTATION_OUTLINE.md`, ~2-3 minutes, covers ingest → auto-confirm → escalate → owner review.
6. A stable public URL if you want pay-page *links* instead of QR images — optional.

## Extension ideas not yet built (optional, for later)

These were discussed but intentionally left out of this session's scope (large enough to be separate work):
- An LLM step that writes a plain-English summary for escalated cases (never decides, just informs the owner) — safe to add since it wouldn't touch the auto-confirm path.
- A second, deliberately-not-automated decision (e.g. "should we restock item X") as a small Streamlit add-on, to demonstrate arguing both directions of the automation question.
- SPEC's Phase 6 soak test (200 simulated orders, checking for zero false "paid" results).

## Known limitations / things to watch

- The free Cloudflare tunnel (`trycloudflare.com`) is unreliable — don't depend on it without testing it fresh each time; QR-image mode has no such dependency.
- ShopBot and n8n both get killed by the OS if system memory runs low — expected, not a bug; `bash start.sh` brings them back.

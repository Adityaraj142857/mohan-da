# Decisions and deviations from `flow/SPEC.md`

Per SPEC §0.4 ("reality beats this spec"), every deviation is logged here.

## `docs/assignment/` — course assignment deliverables (2026-09-20)

Added a `docs/assignment/` folder containing the Problem Brief, Automation
Argument, n8n workflow (Path A), test results and presentation outline for
`flow/Assignment.pdf` (Team Assignment: Business Analytics — Decision
Support or Agentic Automation). This is course-submission material layered
on top of the ShopBot project, not a SPEC requirement; it deliberately
scopes the "automation" question to one real decision already central to
ShopBot's design — *"is this order paid, or does it need a human?"* — and
wraps ShopBot's existing, tested decision engine (`verify/matcher.py`,
`verify/sms_parsers/`) in an n8n pipeline rather than reimplementing the
logic a second time in n8n natively. See `docs/assignment/README.md`.

## Added files not in SPEC's repo layout (§4.2)

- `src/shopbot/harness.py` — a shared test/demo harness (DB + engine +
  simulator channel wiring) used by both `tools/seed_demo.py` and the
  pytest scenario suite, so the two never drift out of sync. Not customer-
  or owner-facing.
- `src/shopbot/verify/screenshot/ocr/factory.py` — a small `make_ocr_engine`
  selector so `OCR_ENGINE` config maps to an engine class in one place.
- `src/shopbot/verify/sms_parsers/registry.py` — the sender→parser lookup
  described in SPEC §11.2 step 10, split out of `generic.py` for clarity.

## Templating library API

Starlette's `Jinja2Templates.TemplateResponse` in the version pinned here
only accepts the newer `(request, name, context)` argument order (the
older `(name, {"request": request, ...})` form some older docs show has
been removed). All template renders in `api/app.py` and `admin/routes.py`
use the new order.

## Unique-amount near-miss flagging (SPEC §11.4/11.7)

When a bank credit doesn't exactly match any pending order, SPEC's
pseudocode says: "keep credit UNMATCHED; if a near-miss order exists...
NEEDS_OWNER". This is implemented as: look at pending orders active in the
credit's time window whose payable amount differs from the credit by no
more than ₹50 (`NEAR_MISS_MAX_DIFF_PAISE` in `verify/matcher.py`), and flag
only if there is exactly one such order. We deliberately do **not** flag
every unrelated pending order in the shop just because one credit didn't
match anything — SPEC's own abuse table (§11.7) says an unrelated credit
should simply sit in "Unmatched credits".

## OCR runs on the original screenshot bytes

SPEC §11.5 step 1 downsizes/normalizes the image before further
processing; this implementation still fingerprints and stores the
normalized/re-encoded version, but runs OCR on the original bytes the
customer sent. This keeps the `FakeOcrEngine` test double simple (it keys
off the exact bytes passed to `.run()`) and avoids a lossy re-encode before
text extraction.

## Vendored htmx (SPEC §4.1)

The spec suggests vendoring `htmx` for the admin/pay-page UI. This build
uses plain `fetch`/`setInterval` JavaScript instead (see `pay.html`,
`sim.html`) — zero dependencies, no CDN, and simpler to audit for a
non-technical owner's one file. Functionally equivalent for this app's
needs (polling a status endpoint, submitting small forms).

## WhatsApp Cloud API adapter is unverified against a live account

`channels/whatsapp_cloud.py` and the `/webhook/whatsapp` routes are
implemented to spec (signature verification, media upload/download,
idempotency) but have not been exercised against a real Meta developer
app, since that requires the owner's own WhatsApp Business setup (SPEC
§13.2, `docs/GO_LIVE.md`). Test it against a real test number before
relying on it.

## Graph API version

`WHATSAPP_API_VERSION` defaults to empty and falls back to `v20.0` in code
if unset — SPEC explicitly warns not to hard-code a version from memory.
**Verify the currently supported version in Meta's docs before go-live**
and set it in `.env`.

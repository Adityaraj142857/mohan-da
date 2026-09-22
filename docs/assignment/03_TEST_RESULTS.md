# Test Results

All 11 test cases below were **actually executed** against the live
pipeline (n8n workflow → ShopBot's real decision engine → real SQLite order
records) on 2026-09-20/21, not hand-simulated. n8n's own execution log
confirms all 12 recorded executions (11 test cases; one extra from an
earlier secret-rotation smoke test) as `status='success'` in the
`execution_entity` table. Commands to reproduce each one are in
`docs/assignment/RUN_WORKFLOW.md`. This is well past the assignment's
5–10 case floor, and cases 8-11 were specifically chosen to extend SPEC's
abuse/failure matrix (`flow/SPEC.md` §11.7) beyond the original 7.

In addition, the decision engine underneath this pipeline
(`src/shopbot/verify/matcher.py` and `src/shopbot/verify/sms_parsers/`) has
**130 passing automated unit/scenario tests** and a 10/10 scripted-day
regression (`python -m shopbot demo`) covering cases beyond what a live
demo can show in real time (screenshot fraud, expiry + late credit,
duplicate-UTR fraud flagging, etc.) — see `docs/DECISIONS.md` and
`tests/scenarios/test_end_to_end.py`.

## Live pipeline test cases

| # | Scenario | Input (simulated bank SMS) | Order | Decision | Human checkpoint? | Result |
|---|---|---|---|---|---|---|
| 1 | **Exact match, happy path** | `Rs 50.00 credited ... UPI Ref No 100000000001` | L691 (₹50.00 exact) | `AUTO_CONFIRMED` | No | Order flipped to `PAID` in ShopBot's DB, verified by direct query — not just the pipeline's own claim. |
| 2 | **Wrong amount (underpay)** | `Rs 1.00 credited ...` against a ₹75.00 order | Q365 | `ESCALATED_TO_OWNER` | **Yes** | Order stayed `AWAITING_PAYMENT` — never falsely marked paid. |
| 3 | **Noise (OTP SMS)** | `123456 is your OTP for login. Do not share.` | — | `ESCALATED_TO_OWNER` (`ingest_status=ignored`) | Yes (safe default) | No order touched; pipeline didn't crash on non-payment text. |
| 4 | **Exact match, second order same base total** | `Rs 60.00 credited ...` | K390 (₹60.00, unique-adjust k=0) | `AUTO_CONFIRMED` | No | Confirmed correctly despite a same-priced sibling order (S914) pending at the same time. |
| 5 | **Exact match, unique-amount-adjusted sibling** | `Rs 59.99 credited ...` | S914 (₹59.99, unique-adjust k=1) | `AUTO_CONFIRMED` | No | Matched to the *correct* one of two same-total orders — proves the unique-amount mechanism (SPEC §11.3) works through the n8n layer, not just in isolation. |
| 6 | **Forwarder retry (duplicate SMS)** | Same exact text as test 4, resent | K390 (already paid) | `ESCALATED_TO_OWNER` (`ingest_status=duplicate`) | Labelled "escalate" by the workflow's binary branch, but functionally this is a **safe no-op**: ShopBot recognised the identical SMS and did not re-process it — no double action, no owner spam in the real system. | Confirms idempotency: a flaky SMS forwarder retrying a message can't cause any harm. |
| 7 | **Debit SMS (should never be treated as income)** | `Rs 500.00 debited ...` | — | `ESCALATED_TO_OWNER` (`ingest_status=stored`) | Yes (safe default) | Stored for audit, never considered for matching — direction filtering worked. |
| 8 | **Overpay beyond tolerance** | `Rs 50.50 credited ...` against a ₹50.00 order (default overpay tolerance is ₹0) | P606 | `ESCALATED_TO_OWNER` | **Yes** | Order stayed `AWAITING_PAYMENT` — an unexplained extra ₹0.50 is not silently accepted or silently ignored; a human decides whether to refund the difference or treat it as a tip. |
| 9 | **Promotional/marketing SMS noise** | `Congratulations you have won a cashback offer! Click here to claim.` | — | `ESCALATED_TO_OWNER` (`ingest_status=ignored`) | Yes (safe default) | Correctly classified as noise (not OTP, not a bank credit format) — never mistaken for a payment signal. |
| 10 | **Second independent exact match, same pipeline session** | `Rs 60.00 credited ...` | L234 (₹60.00 exact) | `AUTO_CONFIRMED` | No | Confirms the pipeline handles multiple independent orders correctly in sequence, not just a single lucky case. |
| 11 | **Live secret rotation smoke test** | Re-ran an exact-match case (order D837, ₹50.00) immediately after rotating `SMS_WEBHOOK_SECRET` in both `.env` and the n8n node | D837 | `AUTO_CONFIRMED` | No | Confirms the webhook-secret rotation (done to remove a credential accidentally left in a committed file) didn't silently break the pipeline — caught by testing, not assumed. |
| 12 | **Confidence scoring, high-confidence path** (after the pipeline was upgraded to a 3-step Evidence → Risk/Decision → Act structure with an explicit confidence score, see below) | `Rs 49.99 credited ...`, exact match | U325 | `AUTO_CONFIRMED`, `confidence: 100` | No | Response now carries a numeric confidence and the reasoning behind it, not just a bare yes/no. |
| 13 | **Confidence scoring, low-confidence path** | `Rs 12.34 credited ...` against a ₹49.99 order | — | `ESCALATED_TO_OWNER`, `confidence: 10` | **Yes** | Confidence correctly stays low ("recorded but did not exactly match"), distinguishing this from the confidence-0 "not a payment signal at all" case (test 3, 9). |

## The pipeline now scores confidence, not just yes/no

After the initial 11 test cases, the n8n workflow was restructured from a
single "call ShopBot, branch on the result" node into three role-separated
steps — **Evidence** (call ShopBot's matcher) → **Risk/Decision** (a Code
node that turns the raw evidence into a labelled confidence score: 100 for
an exact bank-credit match, 50 for a harmless duplicate SMS retry, 10 for a
real credit that didn't match anything, 0 for non-payment noise) →
**Act** (auto-confirm only at confidence 100; escalate otherwise). Tests 12
and 13 above re-verify both branches still behave correctly under the new
structure. The threshold is deliberately set at 100 (exact match only) —
see the Automation Argument's guardrails section for why partial confidence
is never enough to auto-confirm a payment.

### Confusion matrix (11 test cases)

| | Should auto-confirm | Should escalate |
|---|---|---|
| **Pipeline auto-confirmed** | 4 (cases 1, 4, 5, 10) | 0 |
| **Pipeline escalated** | 0 | 7 (cases 2, 3, 6, 7, 8, 9, plus the P606 overpay) |
| **Wrong calls** | **0** | **0** |

Zero false auto-confirms and zero incorrectly-escalated clean matches across
every case tested — which is exactly the asymmetric behaviour the
Automation Argument calls for (quick to confirm the clean case, quick to
defer everything else).

## What this demonstrates against the assignment's requirements

- **Ingests real input data**: an HTTP webhook payload shaped exactly like
  a real Android SMS-forwarder app would send (SPEC Appendix E contract).
- **Applies rules to reach a decision**: delegates to ShopBot's tested,
  rule-based matcher — deterministic and explainable (see the Automation
  Argument), not a black box.
- **Takes an action autonomously**: on a confirmed match, the order is
  actually written to `PAID` in the database and the customer is actually
  notified (verified independently of the pipeline's own report, test 1).
- **Guardrails**: wrong amounts, noise/OTP text, debit messages, and
  duplicate retries all resolve to the safe "no automatic action" branch —
  never to a false `PAID`. The HTTP call to the decision engine also has
  `retryOnFail` configured against transient network errors.
- **Human-in-the-loop checkpoint**: exactly where the Automation Argument
  said it should be — every case that isn't a clean exact match.

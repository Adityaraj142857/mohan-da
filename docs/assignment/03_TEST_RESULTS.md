# Test Results

All 7 test cases below were **actually executed** against the live pipeline
(n8n workflow → ShopBot's real decision engine → real SQLite order records)
on 2026-09-20, not hand-simulated. n8n's own execution log confirms 7/7
recorded as `success` (executions 1-7, `execution_entity` table). Commands
to reproduce each one are in `docs/assignment/RUN_WORKFLOW.md`.

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

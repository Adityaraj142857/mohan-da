# Assignment deliverables — Business Analytics: Decision Support or Agentic Automation

Business: MohanDa's Tuck Shop, Ramanujan Hostel, IIM Calcutta.
Path chosen: **Path A — agentic automation, via n8n.**

| Deliverable (per `flow/Assignment.pdf`) | File |
|---|---|
| 1. Problem Brief (1 page) | [`01_PROBLEM_BRIEF.md`](01_PROBLEM_BRIEF.md) |
| 2. Automation Argument (1-2 pages) | [`02_AUTOMATION_ARGUMENT.md`](02_AUTOMATION_ARGUMENT.md) |
| 3. Working Build (n8n workflow) | [`n8n_workflow.json`](n8n_workflow.json) — how to run it: [`RUN_WORKFLOW.md`](RUN_WORKFLOW.md) |
| 4. Test Results (5-10 cases) | [`03_TEST_RESULTS.md`](03_TEST_RESULTS.md) |
| 5. Team Presentation | [`04_PRESENTATION_OUTLINE.md`](04_PRESENTATION_OUTLINE.md) |
| 6. Individual Reflection (optional) | [`05_INDIVIDUAL_REFLECTION_TEMPLATE.md`](05_INDIVIDUAL_REFLECTION_TEMPLATE.md) |

## Why this decision, and why n8n

The automation argument (`02_AUTOMATION_ARGUMENT.md`) is scoped to one
specific decision inside the larger ShopBot project this team built:
**"is this order paid, or does it need a human?"** The argument concludes a
hybrid — automate the clean, bank-confirmed exact-match case; escalate
everything ambiguous to the shop owner.

The n8n workflow is the Path A artifact that *acts on* that argument: it
ingests a bank-credit event, calls ShopBot's own tested decision engine
(the same code backing the shop's real payment flow — not a mock built
just for this assignment), branches on the outcome, and either confirms
the order autonomously or escalates to a human checkpoint. This means the
automation being graded here is a real decision from a real, working
system, not a toy example built only to satisfy the assignment.

## Quick facts for grading / Q&A

- The decision engine (`src/shopbot/verify/matcher.py`,
  `src/shopbot/verify/sms_parsers/`) has **130 passing automated tests**
  (`pytest`) plus a 10/10 scripted regression day (`python -m shopbot demo`)
  — the n8n pipeline calls this tested logic rather than reimplementing it.
- All 7 test cases in `03_TEST_RESULTS.md` were run against the live
  pipeline on 2026-09-20, with n8n's own execution log and ShopBot's
  database confirming the outcomes independently of each other.
- The wider ShopBot system (order-taking, pricing, UPI payment, screenshot
  fraud checks, owner console) is documented in `flow/SPEC.md`,
  `flow/PROBLEM_STATEMENT.md`, `README.md`, and `docs/DECISIONS.md` — this
  assignment folder focuses only on the one decision + the required
  automation-tool artifact.

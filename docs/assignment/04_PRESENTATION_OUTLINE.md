# Presentation outline

One slide per section below is enough for a short in-class presentation;
expand any section if your instructor gives more time.

### 1. The problem (1 slide)
MohanDa's Tuck Shop, Ramanujan Hostel, IIM Calcutta — real shop, real menu
(70 items), takes orders over WhatsApp, collects UPI payment. **Before
starting any order, the owner must manually check a bank statement to
confirm the money actually arrived** — screenshots aren't trustworthy proof.
Slow, doesn't scale, depends on a relative's phone. *(Source: `01_PROBLEM_BRIEF.md`)*

### 2. The decision we chose to analyze (1 slide)
Not "automate the whole shop" — one specific, well-scoped decision:
**"Is this order paid — yes, or does a human need to check?"**
Made dozens of times a day, by one person, today entirely by hand.

### 3. The automation argument (1-2 slides)
Walk through the 6-factor table (`02_AUTOMATION_ARGUMENT.md`). Key line:
the evidence splits cleanly into two cases —
- **Bank-confirmed exact match** → low-risk, high-frequency, fully
  explainable → **automate it**.
- **Anything ambiguous** (mismatched amount, no match, duplicate, expired)
  → higher stakes per instance, needs judgment → **keep a human**.

**Conclusion: hybrid automation with an explicit human-in-the-loop
checkpoint** — not "automate everything" or "automate nothing."

### 4. The build (1-2 slides)
- **n8n workflow** (Path A): ingest a bank-SMS-shaped webhook → call the
  decision engine → branch on the outcome → act (confirm & notify, or
  escalate to the owner).
- The decision engine itself is ShopBot — a working payment/ordering system
  built for this shop, with 130 passing automated tests, so the pipeline
  isn't calling a toy/mock — it's calling tested, real logic.
- Show the n8n canvas: Ingest → Evidence → Risk/Decision (confidence score)
  → Branch → Act (confirm) / Act (escalate) → Respond.

### 5. Test results (1 slide)
13 live test cases run through the actual pipeline (not hand-waved):
exact match ×4, wrong amount, overpay, OTP/promo noise ×2, duplicate SMS
retry, debit SMS, plus the confidence-scoring upgrade re-verified on both
branches. Zero wrong calls across all of them (see the confusion matrix in
`03_TEST_RESULTS.md`) — confirm only the clean case, escalate everything
else, never a false PAID.

### Screen recording (record this, ~2-3 minutes, before submission)
1. `/sim` — place an order as a demo customer, confirm it, see the pay QR.
2. n8n — send a matching bank-SMS webhook call, show the execution log:
   Ingest → Evidence → Risk/Decision (confidence: 100) → Act (auto-confirm).
3. `/sim` again — the "Payment received ✅" message arriving live; `/admin`
   board showing the order under PAID.
4. n8n — send a **mismatched** amount instead, show confidence dropping and
   the branch going to Escalate.
5. `/admin/needs-attention` — the escalated order sitting there for the
   owner to approve/reject by hand.
That sequence alone demonstrates ingestion, reasoning, autonomous action,
and the human-in-the-loop checkpoint — the whole automation argument in
one take.

### 6. What we'd do differently at scale (1 slide, optional)
- Real bank SMS forwarder app instead of a simulated webhook payload.
- n8n error-branch on the HTTP node for ShopBot downtime (currently retried,
  not yet branched) — noted as a limitation, not hidden.
- The same "explain the factors, keep humans on ambiguous cases" pattern
  generalizes to the shop's other manual decision, screenshot fraud
  checking, already built the same way inside ShopBot (owner-review queue).

---

## Team presentation checklist
- [ ] Assign one section per person (5 sections, 5 members).
- [ ] Have the live demo ready per `RUN_WORKFLOW.md` — or a screen
      recording as backup if live demo risk is a concern.
- [ ] Practice the Q&A: be ready to explain *why* the 6-factor table
      concluded a hybrid, not a blanket answer — that reasoning, not the
      code, is 25% of the rubric on its own.

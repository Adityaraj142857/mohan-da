# Automation Argument

**Decision in scope:** *"Should this order be marked PAID (and released for
preparation), or does it need a human to look at it?"*

**Scope note (read this first):** the graded artifact here is this one
decision and the n8n pipeline that automates it — not the shop's entire
ordering system. ShopBot (the larger app referenced throughout this report,
with its menu parsing, WhatsApp-style chat, and owner console) exists as
supporting infrastructure that makes this decision real and testable: it is
what generates genuine orders with genuine payable amounts and genuine bank
credits for the automation to act on, rather than a synthetic example built
only for this assignment. The automation being evaluated is specifically
the n8n workflow in `n8n_workflow.json` and the reasoning below.

We deliberately scope the argument to this one decision — not the whole
ordering workflow — because the assignment's own guidance is to test each
decision against the six factors, and "confirm this specific payment" is
where the real risk in MohanDa's business sits.

## Argument, factor by factor

| Factor | Analysis | Verdict |
|---|---|---|
| **Reversibility** | Two different sub-cases behave very differently. If the bank's own SMS shows an exact credit matching an order's amount, that fact does not need "reversing" — it already happened; there is nothing left to decide. If instead the evidence is ambiguous (two orders with the same amount, an amount mismatch, a screenshot with no matching bank credit yet), a wrong automatic call means handing over free food — a real, uncomfortable-to-reverse loss for a small shop. | **Split.** Low-risk to automate the exact-match case; high-risk to automate the ambiguous case. |
| **Data quality & availability** | The bank credit SMS is issued by the bank itself, arrives independent of the customer, and states amount + a unique transaction reference (UTR) — this is clean, structured, authoritative data. The customer's screenshot, by contrast, is self-reported, easy to edit, and (per published payment-industry guidance) is *never* proof of a transaction on its own. | **Good enough to automate** only when we use the bank-SMS data path; **not good enough** to automate off the screenshot alone. |
| **Legal & ethical risk** | Financial harm (giving away food for an unpaid order) is direct and immediate; there is no discrimination/fairness dimension (the decision doesn't concern a person's characteristics, just whether money arrived) and no regulatory approval process applies to a shop's own order-fulfilment logic. The main ethical obligation is simply: **never tell a customer "paid" when it isn't true.** | **Moderate risk**, fully mitigated by making the automated path a *strict, symmetric* rule (exact amount + evidence from the bank itself) rather than a probabilistic guess. |
| **Stakes & frequency** | Very high frequency (every order, dozens/day) and, for the *exact-match* case, genuinely low stakes (the rule is simple and deterministic: this bank credit's amount equals this order's exact payable amount). The ambiguous case is comparatively rare but higher-stakes per instance. | High-volume, low-stakes matches are a **textbook automation candidate**; the residual ambiguous cases are the opposite (low-volume, higher-stakes → keep human judgment). |
| **Explainability** | "This exact amount arrived by bank credit within the payment window" is a one-sentence justification any customer or the owner could be given if challenged. Compare that to "the screenshot looked convincing" — which is not a defensible justification at all. | **Fully explainable** for the bank-evidence path; this is what makes it a safe rule to automate. |
| **Human judgment / context** | Recognising *when the evidence itself is insufficient* (two pending orders share a total, a screenshot shows a different payee, a payment arrives after the order expired) requires exactly the kind of judgment a rule can't safely resolve alone — those cases should go to a person, every time. | **Required** for the exception cases; **not required** for the clean-match case. |

## Conclusion

The evidence does not support a single yes/no answer for "automate payment
confirmation" — it supports a **hybrid**, and the factor-by-factor analysis
above is precisely why:

> **Automate** the narrow, high-frequency, fully-explainable, easily-reversible
> sub-decision — *"does a bank-confirmed credit exactly match this order's
> amount, within its payment window?"* — because it is deterministic,
> auditable, and backed by authoritative data.
>
> **Do not automate** — and instead escalate to the shop owner — every case
> where the evidence is ambiguous, missing, or contradictory: two orders
> with the same amount, an amount that doesn't match anything pending, a
> payment that arrives after the order's deadline, or a screenshot whose
> claims don't hold up. These are exactly the low-volume, higher-stakes,
> judgment-dependent cases the factors above say a human should own.

This is a deliberately conservative automation boundary: the system is
allowed to say "confirmed" only when it can also say *why*, and is required
to say "please check this" the moment it can't. That asymmetry — quick to
confirm, quick to defer — is the whole design, and it is what the working
build (Section 3) implements as an n8n pipeline with an explicit
human-in-the-loop checkpoint.

## Guardrails: edge cases, low-confidence outputs, errors, and where a human checkpoint sits

The assignment asks explicitly: *what happens on edge cases, low-confidence
outputs, or errors, and where does a human still get a checkpoint?* Here is
the exhaustive answer for this decision — every case below is implemented
in code (`src/shopbot/verify/matcher.py`), covered by an automated test, and
several are also run live through the n8n pipeline (`03_TEST_RESULTS.md`):

| Situation | Confidence | Automated action |
|---|---|---|
| Bank credit exactly matches one pending order's payable amount, within its payment window | High — exact, authoritative match | **Auto-confirm.** No human involved. |
| Two pending orders happen to share the same amount | Ambiguous — evidence can't disambiguate | **Escalate.** Both flagged `NEEDS_OWNER`, shown side by side for the owner to pick. |
| Credit amount is lower than the order (underpaid) or higher by more than the configured tolerance (overpaid) | Low — evidence contradicts the order | **Escalate**, with the expected vs. received amount shown. Never auto-confirm a partial or excessive payment. |
| Credit arrives after the order's payment window has expired, but within a short grace period | Ambiguous — could be a late-but-genuine payment or an unrelated credit | **Escalate** as "late payment"; never silently re-activates an expired order. |
| Same UTR (bank transaction reference) already matched to a different order | High confidence of **fraud**, not of payment | **Escalate** and increment a fraud-flag counter on the customer; never auto-confirm. |
| Same screenshot image (or a near-duplicate) already used on another order | High confidence of fraud | **Reject the claim outright** and flag for fraud review; screenshot alone was never going to confirm payment anyway. |
| SMS forwarder goes offline (no credits arriving at all) | No evidence, not even low-confidence | **Escalate everything** — nothing is ever marked paid by default/timeout. The owner is separately alerted if no heartbeat is seen during open hours. |
| Bank SMS is noise (OTP, promotional, or a debit rather than a credit) | Not applicable — not a payment signal at all | **Ignored** for matching purposes, but still logged for audit; never treated as evidence either way. |
| `BANK_SIGNAL=none` (forwarder not configured yet) | No automatic evidence available at all | **Every payment escalates to the owner by default** — this is the safe fallback configuration for a shop that hasn't set up bank-SMS forwarding yet. |
| A screenshot's own checks look strong (right amount, right payee, UTR present, not a duplicate) but no bank credit has arrived yet | Medium — plausible but not yet confirmed | **Pending, not confirmed.** Customer is told "waiting for bank confirmation"; escalates to the owner automatically after a configurable timeout if the bank credit still hasn't shown up. |

**The single rule that ties all of this together:** the system will only ever
write `PAID` for one of two reasons — (a) a bank credit that is an *exact*
amount match within the payment window, or (b) an explicit, audited owner
action. Every other situation, by construction, routes to a human. This
isn't an assertion — `tests/unit/test_paid_invariant.py` in the codebase
greps the entire source tree and fails the build if any code path other
than those two ever sets an order's status to `PAID`.

## Rough business case (order-of-magnitude, not measured)

These are *deliberately labelled estimates*, not data collected from
Mohan-da — see `docs/OWNER_TODO.md` for the two-minute conversation that
would replace them with real numbers before this ships to real customers.
They're included so the argument isn't purely qualitative.

| Quantity | Rough estimate | Basis |
|---|---|---|
| Manual payment-check time today | ~1–2 minutes/order (open bank app or ask a relative to check, cross-reference amount, reply to customer) | Typical for a manual bank-statement cross-check on a phone |
| Orders/day (assumed, hostel tuck shop) | ~30–60 | Order-of-magnitude for a single-shop hostel tuck counter; not measured |
| Time saved/day if ~90% of orders auto-confirm | ~30–90 minutes/day | (30–60 orders × 90%) × ~1–2 min saved per auto-confirmed order |
| Cost of one missed fake-payment incident | Full cost of the order's ingredients + prep time, unrecovered | The entire reason bank-evidence (not screenshots) gates `PAID` |
| Cost of the automation itself | ₹0 recurring (self-hosted n8n, free bank-SMS forwarder app, no paid LLM in the default path) | Matches SPEC constraint C1/C2 — the shop's whole reason for wanting this |

The precise numbers matter less than the shape of the argument: the
manual step being automated is small-but-frequent (multiplies into real
time saved daily), the failure mode being guarded against is rare-but-costly
(justifies keeping a human checkpoint rather than skipping verification
entirely), and the automation itself adds no recurring cost — which is why
a hybrid, rather than "do nothing" or "automate blindly," is the right
answer for this specific shop.

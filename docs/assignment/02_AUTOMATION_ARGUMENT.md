# Automation Argument

**Decision in scope:** *"Should this order be marked PAID (and released for
preparation), or does it need a human to look at it?"*

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

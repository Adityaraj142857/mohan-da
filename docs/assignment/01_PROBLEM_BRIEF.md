# Problem Brief

**Team assignment — Business Analytics: Decision Support or Agentic Automation**
**Organization:** MohanDa's Stationery & Snacks Tuck Shop, Ramanujan Hostel, IIM Calcutta (est. 1992)
**Contact:** 7003794119 · UPI collection ID: `8602003005@amazonpay`

## The real problem

MohanDa's takes food orders from hostel residents over WhatsApp and collects
payment via UPI. For every single order, before the owner will start
preparing or dispatching food, **someone has to decide: has this customer
actually paid?**

Today that decision is made by hand, every time:

1. The customer sends a payment screenshot on WhatsApp.
2. The owner (or a relative who holds the receiving bank account) opens the
   bank's app/SMS and manually checks whether a matching credit really
   arrived — because a screenshot can be faked with editing apps or
   "fake payment" generator apps, and is not proof of anything.
3. Only after that manual check does the owner start the order.

**Who faces this decision:** the shop owner, unaided — no staff dedicated to
order handling.
**How often:** every order, all day, every day the shop is open — with a
70-item menu and a hostel of residents, this is dozens of times daily.
**What data is available:** (a) the bank's own SMS credit alert — the one
piece of evidence that is actually authoritative; (b) the customer's payment
screenshot — visual, easy to fake, not authoritative; (c) the order's exact
amount and the time the order was placed.
**What happens today:** a fully manual cross-check against a bank statement,
for every order, done by a person (sometimes a relative not directly
involved in the business), with no record kept beyond chat history.

## Why it matters

- **Slow:** the manual check is the single slowest step in fulfilling an
  order — food preparation waits on it.
- **Risky if skipped:** handing over food against a payment that never
  arrived is a direct financial loss; the owner cannot simply trust a
  screenshot.
- **Does not scale:** every additional order adds the same fixed manual
  work: there is no shortcut for "check one more bank statement" as volume
  grows.
- **Depends on a third party:** the account currently receiving payments
  belongs to a relative, who must be personally available to check it —
  a single point of failure and a privacy/consent concern in its own right.
- **No record:** there is no ledger of which orders were paid, when, or by
  what evidence — reconciliation and fraud pattern detection are impossible
  after the fact.

Full background, current-process walkthrough and stakeholder list:
[`flow/PROBLEM_STATEMENT.md`](../../flow/PROBLEM_STATEMENT.md).

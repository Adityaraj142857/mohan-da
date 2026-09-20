# Bank SMS formats

Bank SMS wording differs by bank and even by SMS aggregator (SPEC §3.7).
The four fixtures shipped in `flow/SPEC.md` Appendix D (and mirrored in
`tests/fixtures/sms/appendix_d.py`) are **illustrative only** — not any
real bank's actual format. You must tune this against your own bank.

## How to test your bank's real SMS

1. Get 5-10 real credit SMS from the phone that receives your bank's
   alerts (redact the account number if sharing with anyone else).
2. Run each one through:
   ```bash
   python -m shopbot.tools.test_sms "<paste the sms text>" --sender <sender-id>
   ```
   It prints which parser fired and what it extracted (amount, UTR, payer
   hint, transaction time).
3. If direction/amount/UTR come out wrong, either:
   - Adjust the shared patterns in `src/shopbot/verify/sms_parsers/generic.py`
     (amount regex, UTR label list, credit/debit keyword lists), or
   - Add a bank-specific module under
     `src/shopbot/verify/sms_parsers/banks/your_bank.py` exporting
     `SENDER_REGEX`, `BANK_NAME`, and a `parse(body, received_at)` function
     (see `demo_bank_1.py` for the shape), and register it in
     `src/shopbot/verify/sms_parsers/registry.py`.
4. Set `BANK_SMS_SENDERS` in `.env` to a regex matching only your bank's
   real sender ID(s) — the default `.*` accepts everything, which is fine
   for the demo but should be tightened for real use so unrelated SMS
   (OTPs, promos from other senders) can't reach the parser at all.

## What gets stored

Only a **redacted** copy of the SMS text is stored (`credits.raw_redacted`)
— account/card digit runs of 6+ are masked to their last 4 digits, except
the UTR itself which is kept visible for owner review. Full untouched SMS
bodies are never persisted or logged (SPEC §14).

## Noise filtering

Messages containing OTP/loan/offer/cashback/promo language are parsed as
`ignored` and never considered for payment matching. Debit messages are
stored (for the audit log) but never matched to an order.

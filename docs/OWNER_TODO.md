# Owner TODO

Things only you (the shop owner) can fill in or decide, per `flow/SPEC.md` §0.2.

## Must do before real customers use this

- [ ] Replace `menu.yaml` with your real menu, prices and hostel names.
- [ ] Set `.env`: `SHOP_NAME`, `UPI_VPA`, `PAYEE_NAME` (+ `PAYEE_NAME_ALIASES`
      if your name shows up differently in different apps), `HOSTELS`,
      `DELIVERY_FEE_PAISE`, `OPEN_HOURS`.
- [ ] Generate real, random values for `SMS_WEBHOOK_SECRET` and
      `ADMIN_PASSWORD` — do not keep the `dev-*-change-me` demo defaults.
      `python -m shopbot run` refuses to start on a non-simulator channel
      while these are left at the defaults.
- [ ] Decide which bank account/phone receives payments, and confirm you
      (or whoever holds that phone) can install an SMS-forwarder app on it
      and consents to forwarding bank credit alerts. See §12 of
      `flow/PROBLEM_STATEMENT.md` — if it's a relative's account, this is
      as much a privacy/consent decision as a technical one.
- [ ] Collect 5-10 of your **real** bank credit SMS (you can redact the
      account number/name) and run them through
      `python -m shopbot.tools.test_sms "<sms text>"`. If your bank's
      wording isn't parsed correctly, that's expected — tune the regexes in
      `src/shopbot/verify/sms_parsers/generic.py` or add a bank-specific
      module under `src/shopbot/verify/sms_parsers/banks/` and record the
      real (redacted) format in `docs/SMS_FORMATS.md`.
- [ ] Collect ~20 real (redacted) payment screenshots from GPay/PhonePe/
      Paytm and run `python -m shopbot.tools.eval_screenshots <folder>`.
      **Do not** enable `SCREENSHOT_POLICY=auto_approve_if_strong` unless
      this reports ≥90% accuracy on amount/UTR/status AND you accept the
      residual risk — it is off by default for a reason (SPEC 3.1).
- [ ] Test the UPI deep link (`upi://pay?...`) on real phones with GPay,
      PhonePe and Paytm — personal-VPA prefill behaviour can differ per
      app. Record what you find in `docs/DECISIONS.md`.
- [ ] Decide `UNIQUE_AMOUNT_MODE`: `discount` (default, you absorb up to
      ~₹0.30/order, customers never pay more) vs `off` (exact amounts,
      more manual review when totals collide).
- [ ] Fill in the baseline facts in `flow/PROBLEM_STATEMENT.md` §10
      (orders/day, average order value, minutes spent per order today) so
      you can judge whether this is actually saving you time.

## Before connecting to real WhatsApp customers

- [ ] Follow `docs/GO_LIVE.md` end to end.
- [ ] Re-check Meta's current WhatsApp Cloud API pricing — the spec's
      "1,000 free messages/month" figure is a snapshot and may be wrong by
      the time you read this.
- [ ] Decide whether the optional `/order` web page (SPEC 13.4) is worth
      building — it cuts WhatsApp message costs and parsing errors.

## Placeholders currently in the repo

- `menu.yaml` — SPEC Appendix A's dummy menu.
- `.env.example` — every value marked "PLACEHOLDER" must be replaced in
  your own `.env` (which is git-ignored).
- `flow/SPEC.md` Appendix D bank SMS samples are illustrative only; they
  are not any real bank's actual format.

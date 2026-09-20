# Going live on WhatsApp (SPEC §13.2, §13.3)

ShopBot works fully as a demo with `CHANNEL=simulator` and no external
accounts. This document is only needed once you want real WhatsApp
customers.

## 1. Test setup (free, up to 5 recipients)

1. Create a [Meta developer app](https://developers.facebook.com/apps) and
   add the **WhatsApp** product.
2. Note the auto-created **test number** and its **Phone Number ID**.
3. Add up to 5 recipient phone numbers (yours, a few friends/family) —
   each confirms via a code sent to their WhatsApp.
4. Create an access token. The quick-start token is temporary (expires in
   ~24h); create a **system-user token** for a long-lived one.
5. Set `.env`: `CHANNEL=whatsapp`, `WHATSAPP_TOKEN`,
   `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN` (any string you
   pick), `WHATSAPP_APP_SECRET` (from the app's Basic Settings).
6. **Look up the currently supported Graph API version** in Meta's docs
   and set `WHATSAPP_API_VERSION` — do not trust a version hard-coded from
   memory (it changes over time and old versions get deprecated).
7. Get a public URL (see `docs/DEPLOY_FREE.md`) and set `PUBLIC_BASE_URL`.
8. In the Meta app, set the webhook callback URL to
   `<PUBLIC_BASE_URL>/webhook/whatsapp` and the verify token to match
   `WHATSAPP_VERIFY_TOKEN`. Subscribe to the `messages` field.
9. Restart ShopBot (`python -m shopbot run`) and message the test number
   from one of the 5 verified recipient phones.

Since free tunnel URLs change on restart, you'll need to re-paste the
webhook callback URL in the Meta app each time you restart the tunnel.

## 2. Production checklist

- [ ] A dedicated business phone number (not one already active on the
      regular WhatsApp consumer app) — ask Meta/your BSP about migration
      options if needed.
- [ ] Meta business verification, if/when Meta requires it for your volume.
- [ ] Display name approval for the business profile.
- [ ] A payment method on file with Meta (required once you exceed the
      free tier).
- [ ] **Re-check current WhatsApp Cloud API pricing** before launch — the
      "1,000 free service messages/month, then ~₹0.145 each" figure in
      `flow/SPEC.md` §3.5 is a snapshot from when the spec was written and
      may already be wrong.
- [ ] Opt-in wording for customers before they start receiving messages.
- [ ] A privacy notice line, e.g. "We store your order and payment
      screenshot to confirm payment; deleted after N days" — see
      `MEDIA_RETENTION_DAYS` in `.env` and `python -m shopbot.tools.purge`.
- [ ] Decide whether the optional `/order` web page (SPEC §13.4) is worth
      adding to cut message costs and parsing errors further.

## 3. Message economy

ShopBot logs every outbound message (`outbound_log` table) and the
`/admin/reports` page shows the running count against
`MESSAGE_FREE_ALLOWANCE`, warning at 80%. Optional status pushes (e.g.
"out for delivery") can be disabled if you're close to the limit.

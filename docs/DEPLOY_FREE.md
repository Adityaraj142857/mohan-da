# Getting a free public URL

You need a public HTTPS URL for two things: the pay-page links you send
customers (so WhatsApp will make them tappable, SPEC §3.4), and later the
WhatsApp webhook callback (SPEC §13.2). Both are optional for the local
demo (`CHANNEL=simulator`) but required once you connect real WhatsApp.

## Option 1: Cloudflare quick tunnel (recommended, free, no account needed)

```bash
# macOS: brew install cloudflared
# Windows/Linux: download from developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
cloudflared tunnel --url http://127.0.0.1:8000
```

It prints a random `https://<random>.trycloudflare.com` URL. Put that in
`.env` as `PUBLIC_BASE_URL` and restart ShopBot. **This URL changes every
time you restart the tunnel** — that's expected for the free tier; update
`PUBLIC_BASE_URL` (and the WhatsApp webhook URL, once you're on that) each
time.

## Option 2: ngrok free tier

```bash
ngrok http 8000
```

Same trade-off: free, no fixed domain, URL changes on restart unless you
pay for a reserved domain.

## Option 3: your own domain (stable, not free)

If you already own a domain, a small reverse proxy (Caddy, Cloudflare
Tunnel with a named tunnel bound to your domain) gives you a stable URL.
Out of scope for the ₹0 demo but worth it once you have steady volume.

## Without any public URL

ShopBot still works: it falls back to sending the QR code image directly
(with the UPI ID and amount as text) instead of an https pay-page link.
Customers scan the QR from a second device, or copy the UPI ID and amount
manually. The owner console (`/admin`) and simulator (`/sim`) only need to
be reachable on your own machine or local Wi-Fi (`BIND_HOST=0.0.0.0`), not
the public internet.

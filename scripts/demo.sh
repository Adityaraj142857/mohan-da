#!/usr/bin/env bash
# One-command demo launcher: starts ShopBot + a free Cloudflare tunnel,
# wires the tunnel URL into .env so pay-page links are real tappable
# https links, and prints everything you need for a live demo.
#
# Usage: bash scripts/demo.sh
# Stop everything with Ctrl+C.
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${PORT:-8000}"
LOG_DIR="$(mktemp -d)"
SERVER_LOG="$LOG_DIR/shopbot.log"
TUNNEL_LOG="$LOG_DIR/cloudflared.log"

# --- setup (idempotent) ---------------------------------------------------
if [ ! -d .venv ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi
# shellcheck source=/dev/null
source .venv/bin/activate
pip install -q -e . >/dev/null

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example — edit it with your real menu/UPI ID."
fi

CLOUDFLARED_BIN="$(command -v cloudflared || true)"
if [ -z "$CLOUDFLARED_BIN" ] && [ -x /opt/homebrew/opt/cloudflared/bin/cloudflared ]; then
  CLOUDFLARED_BIN=/opt/homebrew/opt/cloudflared/bin/cloudflared
fi

# --- cleanup on exit -------------------------------------------------------
SERVER_PID=""
TUNNEL_PID=""
cleanup() {
  echo
  echo "Stopping ShopBot..."
  [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null || true
  [ -n "$TUNNEL_PID" ] && kill "$TUNNEL_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Free the port if a previous run is still bound to it.
lsof -ti ":$PORT" 2>/dev/null | xargs -r kill 2>/dev/null || true
sleep 1

# --- start the app ----------------------------------------------------------
echo "Starting ShopBot on port $PORT..."
python -m shopbot run > "$SERVER_LOG" 2>&1 &
SERVER_PID=$!

for _ in $(seq 1 20); do
  if curl -s "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done
if ! curl -s "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then
  echo "ShopBot failed to start. Log:"
  cat "$SERVER_LOG"
  exit 1
fi

# --- start a free public tunnel (optional, best-effort) --------------------
# Free trycloudflare.com tunnels have "no uptime guarantee" (cloudflared's
# own words) and sometimes never become reachable. We verify the tunnel
# actually resolves and answers before trusting it — a link we can't
# confirm works is worse than no link (ShopBot's QR-image fallback always
# works with zero external dependencies).
TUNNEL_URL=""
if [ -n "$CLOUDFLARED_BIN" ]; then
  echo "Starting a free Cloudflare tunnel for a real, tappable pay-page link..."
  "$CLOUDFLARED_BIN" tunnel --url "http://127.0.0.1:$PORT" > "$TUNNEL_LOG" 2>&1 &
  TUNNEL_PID=$!

  CANDIDATE_URL=""
  for _ in $(seq 1 20); do
    CANDIDATE_URL="$(grep -o 'https://[a-zA-Z0-9-]*\.trycloudflare\.com' "$TUNNEL_LOG" | head -1 || true)"
    [ -n "$CANDIDATE_URL" ] && break
    sleep 1
  done

  if [ -n "$CANDIDATE_URL" ]; then
    echo "Got a tunnel URL, verifying it's actually reachable (up to 30s)..."
    for _ in $(seq 1 15); do
      CODE="$(curl -s --max-time 4 -o /dev/null -w '%{http_code}' "$CANDIDATE_URL/healthz" 2>/dev/null || true)"
      [ "$CODE" = "200" ] && TUNNEL_URL="$CANDIDATE_URL" && break
      sleep 2
    done
  fi

  if [ -n "$TUNNEL_URL" ]; then
    if grep -q '^PUBLIC_BASE_URL=' .env; then
      sed -i.bak "s|^PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=$TUNNEL_URL|" .env && rm -f .env.bak
    else
      echo "PUBLIC_BASE_URL=$TUNNEL_URL" >> .env
    fi
    echo "Restarting ShopBot so pay-page links use the tunnel URL..."
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
    python -m shopbot run > "$SERVER_LOG" 2>&1 &
    SERVER_PID=$!
    for _ in $(seq 1 20); do
      curl -s "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1 && break
      sleep 0.5
    done
  else
    echo "Tunnel didn't become reachable in time (Cloudflare's free tunnels sometimes just don't come up) — continuing without one."
    echo "Clearing any stale PUBLIC_BASE_URL from a previous run so old dead links can't linger..."
    kill "$TUNNEL_PID" 2>/dev/null || true
    TUNNEL_PID=""
    if grep -q '^PUBLIC_BASE_URL=' .env; then
      sed -i.bak "s|^PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=|" .env && rm -f .env.bak
    fi
    echo "Restarting ShopBot in QR-image mode (works with zero external dependencies)..."
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
    python -m shopbot run > "$SERVER_LOG" 2>&1 &
    SERVER_PID=$!
    for _ in $(seq 1 20); do
      curl -s "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1 && break
      sleep 0.5
    done
  fi
else
  echo "cloudflared not found — skipping the public tunnel (install with 'brew install cloudflared' for a real pay link)."
fi

ADMIN_PASSWORD="$(grep '^ADMIN_PASSWORD=' .env | cut -d= -f2-)"
SHOP_NAME="$(grep '^SHOP_NAME=' .env | cut -d= -f2-)"

echo
echo "======================================================================"
echo " $SHOP_NAME is ready to demo"
echo "======================================================================"
echo " Local:"
echo "   Simulator (place an order here):  http://127.0.0.1:$PORT/sim"
echo "   Owner console:                    http://127.0.0.1:$PORT/admin"
echo "   Admin password:                   $ADMIN_PASSWORD"
if [ -n "$TUNNEL_URL" ]; then
echo
echo " Public (share this / open on your phone):"
echo "   $TUNNEL_URL/sim"
echo "   $TUNNEL_URL/admin"
echo "   (Pay-page links generated during the demo will use this URL.)"
fi
echo "======================================================================"
echo " Press Ctrl+C to stop everything."
echo

# Keep the script (and background processes) alive.
wait "$SERVER_PID"

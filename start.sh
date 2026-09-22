#!/usr/bin/env bash
# ShopBot — single-file launcher.
#
#   bash start.sh          start everything in the background, open the browser
#   bash start.sh stop     stop everything this script started
#   bash start.sh status   check what's currently running
#
# Starts ShopBot and (if Node.js/n8n are available) the n8n automation
# pipeline, both detached from this terminal (nohup) so closing the
# terminal window does NOT stop them — use `bash start.sh stop` instead.
# Then opens your default browser to the simulator.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

PORT="${PORT:-8000}"
N8N_PORT="${N8N_PORT:-5678}"
RUN_DIR=".run"
mkdir -p "$RUN_DIR"
SHOPBOT_PID_FILE="$RUN_DIR/shopbot.pid"
N8N_PID_FILE="$RUN_DIR/n8n.pid"
SHOPBOT_LOG="$RUN_DIR/shopbot.log"
N8N_LOG="$RUN_DIR/n8n.log"

# Try to find an nvm-installed node/n8n even if this shell hasn't sourced nvm.
find_n8n_bin() {
  if command -v n8n >/dev/null 2>&1; then
    command -v n8n
    return
  fi
  local candidate
  candidate="$(find "$HOME/.nvm/versions/node" -maxdepth 2 -name n8n -path '*/bin/n8n' 2>/dev/null | sort -V | tail -1)"
  [ -n "$candidate" ] && echo "$candidate"
}

open_browser() {
  local url="$1"
  if command -v open >/dev/null 2>&1; then open "$url"                # macOS
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$url"       # Linux
  elif command -v cmd.exe >/dev/null 2>&1; then cmd.exe /c start "$url" # WSL
  else echo "Open this manually: $url"
  fi
}

wait_healthy() {
  local url="$1" tries="${2:-30}"
  for _ in $(seq 1 "$tries"); do
    curl -s -o /dev/null "$url" && return 0
    sleep 1
  done
  return 1
}

pid_running() {
  [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null
}

do_status() {
  if pid_running "$SHOPBOT_PID_FILE"; then
    echo "ShopBot: running (PID $(cat "$SHOPBOT_PID_FILE")) — http://127.0.0.1:$PORT"
  else
    echo "ShopBot: not running"
  fi
  if pid_running "$N8N_PID_FILE"; then
    echo "n8n:     running (PID $(cat "$N8N_PID_FILE")) — http://localhost:$N8N_PORT"
  else
    echo "n8n:     not running"
  fi
}

do_stop() {
  for name in SHOPBOT N8N; do
    local pid_file_var="${name}_PID_FILE"
    local pid_file="${!pid_file_var}"
    if pid_running "$pid_file"; then
      kill "$(cat "$pid_file")" 2>/dev/null
      rm -f "$pid_file"
      echo "Stopped $name."
    fi
  done
  # Also free the ports in case something else is squatting on them from a
  # previous crashed run this script didn't track.
  lsof -ti ":$PORT" 2>/dev/null | xargs -r kill 2>/dev/null || true
  lsof -ti ":$N8N_PORT" 2>/dev/null | xargs -r kill 2>/dev/null || true
}

case "${1:-start}" in
  stop)
    do_stop
    exit 0
    ;;
  status)
    do_status
    exit 0
    ;;
  start) ;;
  *)
    echo "Usage: bash start.sh [start|stop|status]"
    exit 1
    ;;
esac

# --- one-time setup (idempotent) -------------------------------------------
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

# --- start ShopBot, detached from this terminal -----------------------------
if pid_running "$SHOPBOT_PID_FILE"; then
  echo "ShopBot already running (PID $(cat "$SHOPBOT_PID_FILE"))."
else
  lsof -ti ":$PORT" 2>/dev/null | xargs -r kill 2>/dev/null || true
  sleep 1
  echo "Starting ShopBot on port $PORT (background, logs: $SHOPBOT_LOG)..."
  nohup python -m shopbot run > "$SHOPBOT_LOG" 2>&1 < /dev/null &
  disown
  echo $! > "$SHOPBOT_PID_FILE"
fi

if ! wait_healthy "http://127.0.0.1:$PORT/healthz" 30; then
  echo "ShopBot did not become healthy in time. Log:"
  tail -30 "$SHOPBOT_LOG"
  exit 1
fi
echo "ShopBot is up: http://127.0.0.1:$PORT"

# --- start n8n, detached (optional — only if Node/n8n are available) -------
N8N_BIN="$(find_n8n_bin)"
if [ -n "$N8N_BIN" ]; then
  if pid_running "$N8N_PID_FILE"; then
    echo "n8n already running (PID $(cat "$N8N_PID_FILE"))."
  else
    lsof -ti ":$N8N_PORT" 2>/dev/null | xargs -r kill 2>/dev/null || true
    sleep 1
    echo "Starting n8n on port $N8N_PORT (background, logs: $N8N_LOG)..."
    ( export N8N_USER_FOLDER="$PWD/.n8n"; export N8N_SECURE_COOKIE=false
      nohup "$N8N_BIN" start > "$N8N_LOG" 2>&1 < /dev/null & disown
      echo $! > "$N8N_PID_FILE" )
  fi
  if wait_healthy "http://localhost:$N8N_PORT/" 30; then
    echo "n8n is up: http://localhost:$N8N_PORT"
  else
    echo "n8n did not become healthy in time (continuing without it). Log:"
    tail -15 "$N8N_LOG"
  fi
else
  echo "n8n/Node.js not found — skipping the automation pipeline (ShopBot itself still works)."
  echo "Install with: nvm install --lts && npm install -g n8n"
fi

# --- open the browser --------------------------------------------------------
open_browser "http://127.0.0.1:$PORT/sim"

ADMIN_PASSWORD="$(grep '^ADMIN_PASSWORD=' .env | cut -d= -f2-)"
SHOP_NAME="$(grep '^SHOP_NAME=' .env | cut -d= -f2-)"

echo
echo "======================================================================"
echo " $SHOP_NAME is running"
echo "======================================================================"
echo "  Simulator (place an order here):  http://127.0.0.1:$PORT/sim"
echo "  Owner console:                    http://127.0.0.1:$PORT/admin"
echo "  Admin password:                   $ADMIN_PASSWORD"
if [ -n "$N8N_BIN" ]; then
echo "  n8n automation pipeline:          http://localhost:$N8N_PORT"
fi
echo
echo "  Both keep running after you close this terminal."
echo "  Stop everything with:   bash start.sh stop"
echo "  Check status with:      bash start.sh status"
echo "======================================================================"

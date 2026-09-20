#!/usr/bin/env bash
# One-command setup + run for macOS/Linux (SPEC section 0.6, 17).
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -e .

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example — edit it with your real menu/UPI ID before going live."
fi

python -m shopbot run

@echo off
REM One-command setup + run for Windows (SPEC section 0.6, 17).
cd /d "%~dp0.."

if not exist .venv (
    python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -q -e .

if not exist .env (
    copy .env.example .env
    echo Created .env from .env.example — edit it with your real menu/UPI ID before going live.
)

python -m shopbot run

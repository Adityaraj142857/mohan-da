"""CLI entry point: `python -m shopbot <command>` (SPEC 0.6, 17)."""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time


def _port_is_free(host: str, port: int) -> bool:
    probe_host = "127.0.0.1" if host == "0.0.0.0" else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((probe_host, port)) != 0


def _free_port_if_ours(port: int) -> None:
    """Best-effort: if `port` is occupied by a leftover ShopBot/uvicorn
    process from a previous run, kill it so `shopbot run` just works on
    re-run. Never touches a port held by something else — you'll still get
    a clear error in that case."""
    if _port_is_free("127.0.0.1", port):
        return
    try:
        if sys.platform == "win32":
            out = subprocess.run(
                ["netstat", "-ano"], capture_output=True, text=True, timeout=3
            ).stdout
            pids = {
                line.split()[-1]
                for line in out.splitlines()
                if f":{port}" in line and "LISTENING" in line
            }
            for pid in pids:
                info = subprocess.run(
                    ["wmic", "process", "where", f"processid={pid}", "get", "commandline"],
                    capture_output=True, text=True, timeout=3,
                ).stdout
                if "shopbot" in info.lower() or "uvicorn" in info.lower():
                    subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True, timeout=3)
        else:
            pids = subprocess.run(
                ["lsof", "-ti", f":{port}"], capture_output=True, text=True, timeout=3
            ).stdout.split()
            for pid in pids:
                info = subprocess.run(
                    ["ps", "-p", pid, "-o", "command="], capture_output=True, text=True, timeout=3
                ).stdout
                if "shopbot" in info.lower() or "uvicorn" in info.lower():
                    subprocess.run(["kill", "-9", pid], capture_output=True, timeout=3)
        time.sleep(0.5)
    except (OSError, subprocess.SubprocessError):
        pass  # best-effort only; the bind attempt below will surface a clear error


def cmd_run(args: argparse.Namespace) -> int:
    import uvicorn

    from shopbot.api.app import build_app
    from shopbot.config import load_settings

    settings = load_settings()
    if settings.channel != "simulator":
        missing = settings.placeholders_left()
        if missing:
            print(
                "Refusing to start: the following settings are still placeholders: "
                + ", ".join(missing)
                + "\nEdit your .env file, then try again.",
                file=sys.stderr,
            )
            return 1

    _free_port_if_ours(settings.port)
    if not _port_is_free("127.0.0.1", settings.port):
        print(
            f"Port {settings.port} is already in use by something else. "
            f"Stop that process or set PORT=<a free port> in .env, then try again.",
            file=sys.stderr,
        )
        return 1

    app = build_app(settings)
    print(f"ShopBot running: http://{settings.bind_host}:{settings.port}/sim (demo) and /admin (owner console)")
    uvicorn.run(app, host=settings.bind_host, port=settings.port)
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    from shopbot.tools.seed_demo import main as seed_main

    return seed_main()


def cmd_test_sms(args: argparse.Namespace) -> int:
    from shopbot.tools.test_sms import main as test_sms_main

    test_sms_main(args.rest)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shopbot")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Start the web app (simulator + owner console)")
    p_run.set_defaults(func=cmd_run)

    p_demo = sub.add_parser("demo", help="Replay a scripted demo day and print pass/fail")
    p_demo.set_defaults(func=cmd_demo)

    p_sms = sub.add_parser("test-sms", help="Test a pasted bank SMS against the parser")
    p_sms.add_argument("rest", nargs=argparse.REMAINDER)
    p_sms.set_defaults(func=cmd_test_sms)

    return parser


def cli() -> None:
    parser = build_parser()
    args = parser.parse_args()
    sys.exit(args.func(args) or 0)


if __name__ == "__main__":
    cli()

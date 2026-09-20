"""CLI: check a pasted bank SMS against the parser registry (SPEC 11.2).

Usage: python -m shopbot.tools.test_sms "<pasted sms>" [--sender VM-DEMOBK]
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime

from shopbot.verify.sms_parsers.registry import parse_with_registry


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Test a bank SMS against ShopBot's parser")
    parser.add_argument("sms", help="the SMS text, quoted")
    parser.add_argument("--sender", default="VM-DEMOBK", help="sender ID (default: VM-DEMOBK)")
    args = parser.parse_args(argv)

    result, parser_name = parse_with_registry(args.sender, args.sms, datetime.now(UTC))

    print(f"Parser used: {parser_name}")
    print(f"Direction:   {result.direction}")
    if result.direction == "ignored":
        print(f"Reason:      {result.ignored_reason}")
        return
    amount = f"₹{result.amount_paise / 100:.2f}" if result.amount_paise is not None else "(not found)"
    print(f"Amount:      {amount}")
    print(f"UTR:         {result.utr or '(not found)'}")
    print(f"Payer hint:  {result.payer_hint or '(not found)'}")
    print(f"Txn time:    {result.txn_time}")
    print(f"Redacted:    {result.raw_redacted}")


if __name__ == "__main__":
    main(sys.argv[1:])

"""Sender -> parser registry (SPEC 11.2 step 10)."""

from __future__ import annotations

import re
from datetime import datetime

from shopbot.verify.sms_parsers import generic
from shopbot.verify.sms_parsers.banks import demo_bank_1, demo_bank_2, demo_bank_3, demo_bank_4
from shopbot.verify.sms_parsers.generic import SmsParseResult

_BANK_MODULES = [demo_bank_1, demo_bank_2, demo_bank_3, demo_bank_4]


def parse_with_registry(sender: str, body: str, received_at: datetime) -> tuple[SmsParseResult, str]:
    """Returns (result, parser_name) — parser_name is surfaced by
    `tools/test_sms.py` so the owner can see which parser fired."""
    for module in _BANK_MODULES:
        if re.match(module.SENDER_REGEX, sender or ""):
            return module.parse(body, received_at), module.__name__.rsplit(".", 1)[-1]
    return generic.parse_generic(body, received_at), "generic"

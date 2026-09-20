"""Style 2 (SPEC Appendix D): '... credited with INR 60.00 ... from rahul@okaxis (UPI Ref 210987654321) ...'"""

from shopbot.verify.sms_parsers.generic import SmsParseResult, parse_generic

SENDER_REGEX = r"(?i)^(VM|VK|AX|BP)-OKAXIS$"
BANK_NAME = "Demo Bank 2 (OkAxis)"


def parse(body: str, received_at) -> SmsParseResult:
    return parse_generic(body, received_at, bank_name=BANK_NAME)

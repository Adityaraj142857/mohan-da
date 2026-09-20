"""Style 1 (SPEC Appendix D): 'Rs 114.63 credited ... UPI Ref No 123456789012. -DEMO BANK'"""

from shopbot.verify.sms_parsers.generic import SmsParseResult, parse_generic

SENDER_REGEX = r"(?i)^(VM|VK|AX|BP)-DEMOBK$"
BANK_NAME = "Demo Bank"


def parse(body: str, received_at) -> SmsParseResult:
    return parse_generic(body, received_at, bank_name=BANK_NAME)

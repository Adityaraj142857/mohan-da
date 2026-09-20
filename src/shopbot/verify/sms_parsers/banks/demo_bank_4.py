"""Style 4 (SPEC Appendix D): 'Dear Customer, INR 45.50 received ... via UPI on 20-Sep-26. UTR: 456789012345'"""

from shopbot.verify.sms_parsers.generic import SmsParseResult, parse_generic

SENDER_REGEX = r"(?i)^(VM|VK|AX|BP)-DEMOB4$"
BANK_NAME = "Demo Bank 4"


def parse(body: str, received_at) -> SmsParseResult:
    return parse_generic(body, received_at, bank_name=BANK_NAME)

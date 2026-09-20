"""Style 3 (SPEC Appendix D): 'UPI/CR/345678901234/RAHUL K/DEMO/20-09-2026 Rs.85.40 credited to XX1234'"""

from shopbot.verify.sms_parsers.generic import SmsParseResult, parse_generic

SENDER_REGEX = r"(?i)^(VM|VK|AX|BP)-DEMOB3$"
BANK_NAME = "Demo Bank 3"


def parse(body: str, received_at) -> SmsParseResult:
    return parse_generic(body, received_at, bank_name=BANK_NAME)

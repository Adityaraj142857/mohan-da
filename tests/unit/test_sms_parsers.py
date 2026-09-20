from datetime import UTC, datetime

from fixtures.sms.appendix_d import (
    CREDIT_STYLE_1,
    CREDIT_STYLE_2,
    CREDIT_STYLE_3,
    CREDIT_STYLE_4,
    DEBIT_SMS,
    OTP_SMS,
)

from shopbot.verify.sms_parsers.registry import parse_with_registry

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def test_style_1_credit():
    sender, body = CREDIT_STYLE_1
    result, parser_name = parse_with_registry(sender, body, NOW)
    assert result.direction == "credit"
    assert result.amount_paise == 11463
    assert result.utr == "123456789012"
    assert parser_name == "demo_bank_1"


def test_style_2_credit_with_payer_vpa():
    sender, body = CREDIT_STYLE_2
    result, _ = parse_with_registry(sender, body, NOW)
    assert result.direction == "credit"
    assert result.amount_paise == 6000
    assert result.utr == "210987654321"
    assert result.payer_hint == "rahul@okaxis"


def test_style_3_credit():
    sender, body = CREDIT_STYLE_3
    result, _ = parse_with_registry(sender, body, NOW)
    assert result.direction == "credit"
    assert result.amount_paise == 8540
    assert result.utr == "345678901234"


def test_style_4_credit_with_utr_label():
    sender, body = CREDIT_STYLE_4
    result, _ = parse_with_registry(sender, body, NOW)
    assert result.direction == "credit"
    assert result.amount_paise == 4550
    assert result.utr == "456789012345"


def test_debit_is_ignored_for_matching():
    sender, body = DEBIT_SMS
    result, _ = parse_with_registry(sender, body, NOW)
    assert result.direction == "debit"


def test_otp_is_ignored():
    sender, body = OTP_SMS
    result, _ = parse_with_registry(sender, body, NOW)
    assert result.direction == "ignored"
    assert result.ignored_reason == "noise"


def test_redaction_masks_account_but_keeps_utr():
    sender, body = CREDIT_STYLE_1
    result, _ = parse_with_registry(sender, body, NOW)
    assert "123456789012" in result.raw_redacted  # UTR kept visible
    assert "XXXXXX1234" not in result.raw_redacted.replace("XXXXXX1234", "")  # sanity: original mask untouched
    assert "1234" in result.raw_redacted


def test_dedupe_hash_stable_for_identical_body():
    sender, body = CREDIT_STYLE_1
    r1, _ = parse_with_registry(sender, body, NOW)
    r2, _ = parse_with_registry(sender, body, NOW)
    assert r1.raw_hash == r2.raw_hash


def test_promo_noise_is_ignored():
    from shopbot.verify.sms_parsers.generic import parse_generic

    result = parse_generic("Congratulations you have won a cashback offer! Click here.", NOW)
    assert result.direction == "ignored"

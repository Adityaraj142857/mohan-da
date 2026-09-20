from shopbot.menu.pricing import (
    PricedLine,
    delivery_fee_paise,
    payable_paise,
    subtotal_paise,
    total_paise,
)


def test_subtotal():
    lines = [PricedLine("Tea", 1000, 2), PricedLine("Samosa", 1000, 1)]
    assert subtotal_paise(lines) == 3000


def test_delivery_fee_takeout_is_zero():
    assert delivery_fee_paise("takeout", None, 1500) == 0


def test_delivery_fee_delivery_default():
    assert delivery_fee_paise("delivery", "Hostel A", 1500) == 1500


def test_delivery_fee_per_hostel_override():
    assert delivery_fee_paise("delivery", "Hostel C", 1500, {"Hostel C": 2000}) == 2000


def test_total_is_subtotal_plus_fee_only():
    assert total_paise(3000, 1500) == 4500


def test_payable_discount_never_exceeds_total():
    total = 6000
    payable = payable_paise(total, 30, "discount")
    assert payable == 5970
    assert payable <= total


def test_payable_surcharge():
    assert payable_paise(6000, 30, "surcharge") == 6030


def test_payable_off():
    assert payable_paise(6000, 30, "off") == 6000

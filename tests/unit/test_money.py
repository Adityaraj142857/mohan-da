from shopbot.money import format_inr, paise_to_rupees_str, rupees_to_paise


def test_rupees_to_paise_basic():
    assert rupees_to_paise("114.63") == 11463
    assert rupees_to_paise("60") == 6000
    assert rupees_to_paise(60) == 6000
    assert rupees_to_paise("10.5") == 1050
    assert rupees_to_paise("1,114.63") == 111463


def test_paise_to_rupees_str():
    assert paise_to_rupees_str(11463) == "114.63"
    assert paise_to_rupees_str(100) == "1.00"
    assert paise_to_rupees_str(5) == "0.05"


def test_format_inr():
    assert format_inr(11463) == "₹114.63"


def test_roundtrip():
    for paise in [0, 5, 100, 11463, 999999]:
        assert rupees_to_paise(paise_to_rupees_str(paise)) == paise

from urllib.parse import parse_qs, urlparse

from shopbot.payments.upi import build_upi_uri


def test_upi_uri_encoding_and_two_decimals():
    uri = build_upi_uri("shopname@bank", "Shop Owner", 11463, "A123", "ShopBot")
    assert uri.startswith("upi://pay?")
    parsed = urlparse(uri)
    qs = parse_qs(parsed.query)
    assert qs["pa"] == ["shopname@bank"]
    assert qs["pn"] == ["Shop Owner"]
    assert qs["am"] == ["114.63"]
    assert qs["cu"] == ["INR"]
    assert qs["tn"] == ["ShopBot A123"]
    assert "tr" not in qs


def test_upi_uri_whole_rupee_has_two_decimals():
    uri = build_upi_uri("a@b", "Name", 6000, "B456", "Shop")
    qs = parse_qs(urlparse(uri).query)
    assert qs["am"] == ["60.00"]


def test_upi_uri_include_tr():
    uri = build_upi_uri("a@b", "Name", 6000, "B456", "Shop", include_tr=True)
    qs = parse_qs(urlparse(uri).query)
    assert qs["tr"] == ["B456"]


def test_upi_note_truncated_to_40_chars():
    uri = build_upi_uri("a@b", "Name", 100, "X999", "A Very Long Shop Name That Goes On And On")
    qs = parse_qs(urlparse(uri).query)
    assert len(qs["tn"][0]) <= 40

import pytest
from pydantic import ValidationError

from shopbot.config import Settings


def test_defaults_load():
    s = Settings(_env_file=None)
    assert s.channel == "simulator"
    assert s.unique_amount_mode == "discount"


def test_invalid_unique_amount_mode_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, unique_amount_mode="bogus")


def test_placeholders_left_flags_defaults():
    s = Settings(_env_file=None)
    missing = s.placeholders_left()
    assert "UPI_VPA" in missing
    assert "PAYEE_NAME" in missing


def test_placeholders_left_clears_when_set():
    s = Settings(
        _env_file=None,
        upi_vpa="shop@bank",
        payee_name="Shop Owner",
        sms_webhook_secret="a-real-secret",
        admin_password="a-real-password",
    )
    assert s.placeholders_left() == []


def test_hostel_list_parsing():
    s = Settings(_env_file=None, hostels="Hostel A, Hostel B,Hostel C")
    assert s.hostel_list() == ["Hostel A", "Hostel B", "Hostel C"]

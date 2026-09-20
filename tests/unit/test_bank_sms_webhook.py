import tempfile
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from shopbot.api.app import build_app
from shopbot.clock import FakeClock
from shopbot.config import Settings


@pytest.fixture
def client():
    db_path = tempfile.mkstemp(suffix=".db")[1]
    settings = Settings(
        _env_file=None,
        db_path=db_path,
        sms_webhook_secret="my-secret",
        admin_password="admin-pw",
        channel="simulator",
        ocr_engine="fake",
    )
    clock = FakeClock(datetime(2026, 9, 20, 10, 0, tzinfo=UTC))
    app = build_app(settings, clock)
    return TestClient(app)


def test_bank_sms_webhook_wrong_secret_rejected(client):
    resp = client.post("/webhook/bank-sms?key=wrong", json={"from": "VM-DEMOBK", "text": "hi"})
    assert resp.status_code == 401


def test_bank_sms_webhook_stores_credit(client):
    body = {
        "from": "VM-DEMOBK",
        "text": "Rs 60.00 credited to A/c XXXXXX1234 UPI Ref No 123456789012. -DEMO BANK",
        "receivedStamp": "1789900000000",
    }
    resp = client.post("/webhook/bank-sms?key=my-secret", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "stored"


def test_bank_sms_webhook_duplicate_is_idempotent(client):
    body = {"from": "VM-DEMOBK", "text": "Rs 60.00 credited to A/c XXXXXX1234 UPI Ref No 123456789012. -DEMO BANK"}
    r1 = client.post("/webhook/bank-sms?key=my-secret", json=body)
    r2 = client.post("/webhook/bank-sms?key=my-secret", json=body)
    assert r1.json()["status"] == "stored"
    assert r2.json()["status"] == "duplicate"


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200

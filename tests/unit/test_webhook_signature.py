import hashlib
import hmac

from shopbot.channels.whatsapp_cloud import verify_webhook_signature


def test_valid_signature_accepted():
    secret = "app-secret"
    body = b'{"hello":"world"}'
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_webhook_signature(secret, body, sig) is True


def test_invalid_signature_rejected():
    assert verify_webhook_signature("app-secret", b"body", "sha256=deadbeef") is False


def test_missing_signature_rejected():
    assert verify_webhook_signature("app-secret", b"body", None) is False


def test_wrong_prefix_rejected():
    assert verify_webhook_signature("app-secret", b"body", "sha1=abcdef") is False

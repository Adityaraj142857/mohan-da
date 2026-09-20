"""SPEC Definition of Done: 'No code path marks PAID except a matched
credit or an audited owner action (or the explicit auto_approve_if_strong
policy, which is off by default). Add a test that greps/asserts this
invariant.'"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "shopbot"

ALLOWED_ASSIGNERS = {
    "orders/service.py",  # mark_paid() — the single place status becomes PAID
}


def test_only_mark_paid_assigns_order_status_paid():
    pattern = re.compile(r'order\.status\s*=\s*"PAID"')
    offenders = []
    for path in SRC.rglob("*.py"):
        rel = str(path.relative_to(SRC))
        if rel in ALLOWED_ASSIGNERS:
            continue
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            offenders.append(rel)
    assert offenders == [], f"order.status directly set to PAID outside mark_paid() in: {offenders}"


def test_mark_paid_callers_are_credit_match_or_owner_or_documented_auto_policy():
    """Every call site of mark_paid() must be one of: a matched bank credit
    (matcher.py), an owner action (admin/routes.py), or the explicit,
    off-by-default auto_approve_if_strong policy (screenshot/pipeline.py)."""
    allowed_callers = {
        "verify/matcher.py",
        "admin/routes.py",
        "verify/screenshot/pipeline.py",
        "orders/service.py",  # the definition itself
        "harness.py",  # test/demo harness's owner_approve() simulates the owner action
    }
    pattern = re.compile(r"\bmark_paid\(")
    for path in SRC.rglob("*.py"):
        rel = str(path.relative_to(SRC))
        text = path.read_text(encoding="utf-8")
        if pattern.search(text) and "def mark_paid" not in text:
            assert rel in allowed_callers, f"unexpected mark_paid() call site: {rel}"

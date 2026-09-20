import pytest

from shopbot.orders.service import IllegalTransition, validate_transition


def test_legal_chain():
    validate_transition("DRAFT", "AWAITING_PAYMENT")
    validate_transition("AWAITING_PAYMENT", "PAID")
    validate_transition("PAID", "PREPARING")
    validate_transition("PREPARING", "READY")
    validate_transition("READY", "OUT_FOR_DELIVERY")
    validate_transition("OUT_FOR_DELIVERY", "COMPLETED")


def test_illegal_skip_raises():
    with pytest.raises(IllegalTransition):
        validate_transition("DRAFT", "PAID")


def test_terminal_states_have_no_transitions():
    with pytest.raises(IllegalTransition):
        validate_transition("COMPLETED", "PAID")
    with pytest.raises(IllegalTransition):
        validate_transition("CANCELLED", "AWAITING_PAYMENT")


def test_expired_can_resolve_to_paid_for_late_credit():
    validate_transition("EXPIRED", "PAID")

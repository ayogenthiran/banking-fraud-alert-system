from datetime import datetime, timedelta

import pytest

from app.fraud_rules import RECENT_ACCOUNT_LOCATIONS, evaluate_transaction
from app.models import FraudStatus, TransactionRequest, TransactionType


@pytest.fixture(autouse=True)
def clear_location_state():
    """Reset the shared in-memory location store before each test."""
    RECENT_ACCOUNT_LOCATIONS.clear()
    yield
    RECENT_ACCOUNT_LOCATIONS.clear()


def make_transaction(**overrides) -> TransactionRequest:
    """Build a transaction with sensible defaults, overriding as needed."""
    defaults = {
        "account_id": "acc-1",
        "amount": 100.0,
        "transaction_type": TransactionType.DEPOSIT,
        "location": "New York",
        "timestamp": datetime(2026, 1, 1, 12, 0, 0),
        "failed_login_attempts": 0,
    }
    defaults.update(overrides)
    return TransactionRequest(**defaults)


def test_normal_deposit_is_approved():
    transaction = make_transaction(
        transaction_type=TransactionType.DEPOSIT, amount=100.0
    )

    decision = evaluate_transaction(transaction)

    assert decision.status == FraudStatus.APPROVED
    assert decision.risk_score == 0
    assert decision.reasons == []


def test_large_withdrawal_is_flagged():
    transaction = make_transaction(
        transaction_type=TransactionType.WITHDRAWAL, amount=5000.0
    )

    decision = evaluate_transaction(transaction)

    assert decision.status == FraudStatus.FLAGGED
    assert "Unusually large withdrawal amount" in decision.reasons


def test_too_many_failed_logins_is_flagged():
    transaction = make_transaction(failed_login_attempts=3)

    decision = evaluate_transaction(transaction)

    assert decision.status == FraudStatus.FLAGGED
    assert "Too many failed login attempts before transaction" in decision.reasons


def test_different_location_within_window_is_flagged():
    base_time = datetime(2026, 1, 1, 12, 0, 0)

    first = make_transaction(location="New York", timestamp=base_time)
    evaluate_transaction(first)

    second = make_transaction(
        location="London", timestamp=base_time + timedelta(minutes=5)
    )
    decision = evaluate_transaction(second)

    assert decision.status == FraudStatus.FLAGGED
    assert (
        "Transaction from different geographic region within short time window"
        in decision.reasons
    )

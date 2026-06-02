import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.fraud_rules import RECENT_ACCOUNT_LOCATIONS
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_test_state(monkeypatch):
    monkeypatch.setenv("ENABLE_AUTH", "false")
    get_settings.cache_clear()
    RECENT_ACCOUNT_LOCATIONS.clear()
    yield
    get_settings.cache_clear()
    RECENT_ACCOUNT_LOCATIONS.clear()


def test_rejects_non_positive_amount():
    response = client.post(
        "/transactions",
        json={
            "account_id": "acc-1",
            "amount": 0,
            "transaction_type": "deposit",
            "location": "Toronto",
            "timestamp": "2026-06-01T10:00:00",
        },
    )

    assert response.status_code == 422


def test_rejects_invalid_transaction_type():
    response = client.post(
        "/transactions",
        json={
            "account_id": "acc-1",
            "amount": 100,
            "transaction_type": "payment",
            "location": "Toronto",
            "timestamp": "2026-06-01T10:00:00",
        },
    )

    assert response.status_code == 422


def test_rejects_negative_failed_login_attempts():
    response = client.post(
        "/transactions",
        json={
            "account_id": "acc-1",
            "amount": 100,
            "transaction_type": "deposit",
            "location": "Toronto",
            "timestamp": "2026-06-01T10:00:00",
            "failed_login_attempts": -1,
        },
    )

    assert response.status_code == 422


def test_accepts_all_valid_transaction_types():
    for transaction_type in ("withdrawal", "deposit", "transfer"):
        response = client.post(
            "/transactions",
            json={
                "account_id": "acc-1",
                "amount": 100,
                "transaction_type": transaction_type,
                "location": "Toronto",
                "timestamp": "2026-06-01T10:00:00",
            },
        )

        assert response.status_code == 200, transaction_type

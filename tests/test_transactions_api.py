import pytest
from fastapi.testclient import TestClient

from app.fraud_rules import RECENT_ACCOUNT_LOCATIONS
from app.main import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_location_state():
    """Reset shared rule state so API tests do not affect each other."""
    RECENT_ACCOUNT_LOCATIONS.clear()
    yield
    RECENT_ACCOUNT_LOCATIONS.clear()


def make_payload(**overrides):
    payload = {
        "account_id": "acc-api-1",
        "amount": 100.0,
        "transaction_type": "deposit",
        "location": "New York",
        "timestamp": "2026-01-01T12:00:00",
        "failed_login_attempts": 0,
    }
    payload.update(overrides)
    return payload


def test_approved_transaction_returns_expected_decision():
    response = client.post("/transactions", json=make_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["risk_score"] == 0
    assert body["reasons"] == []


def test_large_withdrawal_with_failed_logins_is_flagged(monkeypatch):
    def fake_publish_flagged_transaction(event):
        return {"published": True, "destination": "test"}

    monkeypatch.setattr(
        "app.main.publish_flagged_transaction",
        fake_publish_flagged_transaction,
    )

    response = client.post(
        "/transactions",
        json=make_payload(
            amount=5000.0,
            transaction_type="withdrawal",
            failed_login_attempts=3,
        ),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "flagged"
    assert body["risk_score"] == 80

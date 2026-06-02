import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.fraud_rules import RECENT_ACCOUNT_LOCATIONS
from app.main import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_test_state(monkeypatch):
    """Reset shared state so API tests do not affect each other."""
    monkeypatch.setenv("ENABLE_AUTH", "false")
    get_settings.cache_clear()
    RECENT_ACCOUNT_LOCATIONS.clear()
    yield
    get_settings.cache_clear()
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


def test_health_endpoint_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert "service" in body


def test_approved_transaction_returns_expected_decision():
    response = client.post("/transactions", json=make_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["bank_id"] == "default"
    assert body["risk_score"] == 0
    assert body["reasons"] == []


def test_transaction_works_without_token_when_auth_disabled():
    response = client.post("/transactions", json=make_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["bank_id"] == "default"


def test_transaction_requires_token_when_auth_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_AUTH", "true")
    get_settings.cache_clear()

    response = client.post("/transactions", json=make_payload())

    assert response.status_code == 401


def test_transaction_allows_valid_token_when_auth_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_AUTH", "true")
    get_settings.cache_clear()

    token_response = client.post("/auth/token", json={"account_id": "acc-api-1"})
    token = token_response.json()["access_token"]

    response = client.post(
        "/transactions",
        json=make_payload(),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "approved"


def test_large_withdrawal_with_failed_logins_is_flagged(monkeypatch):
    published_events = []

    def fake_publish_flagged_transaction(event):
        published_events.append(event)
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
    assert body["bank_id"] == "default"
    assert body["risk_score"] == 80
    assert len(published_events) == 1
    assert published_events[0]["bank_id"] == "default"


def test_transaction_response_and_event_include_explicit_bank_id(monkeypatch):
    published_events = []

    def fake_publish_flagged_transaction(event):
        published_events.append(event)
        return {"published": True, "destination": "test"}

    monkeypatch.setattr(
        "app.main.publish_flagged_transaction",
        fake_publish_flagged_transaction,
    )

    response = client.post(
        "/transactions",
        json=make_payload(
            bank_id="bank_b",
            amount=10000.0,
            transaction_type="withdrawal",
            failed_login_attempts=5,
        ),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["bank_id"] == "bank_b"
    assert body["status"] == "flagged"
    assert published_events[0]["bank_id"] == "bank_b"

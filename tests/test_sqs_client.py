import json

import pytest

from app.config import get_settings
from app.sqs_client import publish_flagged_transaction


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch):
    monkeypatch.setenv("SQS_QUEUE_URL", "")
    monkeypatch.setenv("LOCAL_FALLBACK_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_publish_flagged_transaction_writes_local_jsonl(tmp_path, monkeypatch):
    fallback_file = tmp_path / "flagged_transactions.jsonl"
    monkeypatch.setattr("app.sqs_client.LOCAL_FALLBACK_FILE", fallback_file)

    event = {
        "transaction_id": "txn-001",
        "account_id": "acc-1",
        "bank_id": "default",
        "amount": 9000,
        "status": "flagged",
    }

    result = publish_flagged_transaction(event)

    assert result == {"published": True, "destination": "local"}
    lines = fallback_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == event


def test_publish_flagged_transaction_sends_to_sqs(monkeypatch):
    sent_messages = []

    class FakeSQSClient:
        def send_message(self, **kwargs):
            sent_messages.append(kwargs)

    def fake_client(service_name, region_name=None):
        assert service_name == "sqs"
        return FakeSQSClient()

    monkeypatch.setenv("SQS_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/queue")
    get_settings.cache_clear()
    monkeypatch.setitem(
        __import__("sys").modules,
        "boto3",
        __import__("types").SimpleNamespace(client=fake_client),
    )

    event = {"transaction_id": "txn-sqs", "account_id": "acc-2", "status": "flagged"}
    result = publish_flagged_transaction(event)

    assert result == {"published": True, "destination": "sqs"}
    assert len(sent_messages) == 1
    assert sent_messages[0]["QueueUrl"].endswith("/queue")
    assert json.loads(sent_messages[0]["MessageBody"]) == event


def test_publish_flagged_transaction_returns_none_when_disabled(monkeypatch):
    monkeypatch.setenv("LOCAL_FALLBACK_ENABLED", "false")
    get_settings.cache_clear()

    result = publish_flagged_transaction({"transaction_id": "txn-none"})

    assert result == {"published": False, "destination": "none"}


def test_publish_flagged_transaction_requires_sqs_in_aws_environment(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "aws")
    monkeypatch.setenv("SQS_QUEUE_URL", "")
    monkeypatch.setenv("LOCAL_FALLBACK_ENABLED", "false")
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="SQS_QUEUE_URL must be configured"):
        publish_flagged_transaction({"transaction_id": "txn-aws"})

from decimal import Decimal
import importlib
import json
import sys
from types import SimpleNamespace


handler = importlib.import_module("lambda.handler")


def test_dynamodb_conversion_replaces_float_values_with_decimal():
    item = {
        "transaction_id": "txn-001",
        "amount": 100.25,
        "risk_score": 50,
        "reasons": ["Unusually large withdrawal amount"],
        "metadata": {
            "exchange_rate": 1.35,
        },
    }

    converted = handler._to_dynamodb_compatible(item)

    assert converted["amount"] == Decimal("100.25")
    assert converted["metadata"]["exchange_rate"] == Decimal("1.35")
    assert converted["risk_score"] == 50
    assert converted["reasons"] == ["Unusually large withdrawal amount"]


def test_publish_to_firehose_returns_not_configured_when_stream_is_missing(monkeypatch):
    monkeypatch.setattr(handler, "FIREHOSE_STREAM_NAME", "")

    status = handler.publish_to_firehose({"transaction_id": "txn-001"})

    assert status == {"published": False, "destination": "not_configured"}


def test_publish_to_firehose_sends_newline_delimited_json(monkeypatch):
    calls = []

    class FakeFirehoseClient:
        def put_record(self, **kwargs):
            calls.append(kwargs)

    def fake_client(service_name, region_name=None):
        assert service_name == "firehose"
        assert region_name == handler.AWS_REGION
        return FakeFirehoseClient()

    monkeypatch.setattr(handler, "FIREHOSE_STREAM_NAME", "analytics-stream")
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

    transaction = {"transaction_id": "txn-001", "amount": 100.25}
    status = handler.publish_to_firehose(transaction)

    assert status == {"published": True, "destination": "firehose"}
    assert calls[0]["DeliveryStreamName"] == "analytics-stream"

    data = calls[0]["Record"]["Data"].decode("utf-8")
    assert data.endswith("\n")
    assert json.loads(data) == transaction


def test_resolve_bank_id_defaults_when_missing_or_blank():
    assert handler._resolve_bank_id({}) == "default"
    assert handler._resolve_bank_id({"bank_id": None}) == "default"
    assert handler._resolve_bank_id({"bank_id": ""}) == "default"
    assert handler._resolve_bank_id({"bank_id": "   "}) == "default"
    assert handler._resolve_bank_id({"bank_id": "bank_a"}) == "bank_a"
    assert handler._resolve_bank_id({"bank_id": " bank_b "}) == "bank_b"


def test_process_flagged_transaction_preserves_bank_id_for_storage_and_alerts(
    monkeypatch,
    capsys,
):
    stored = []
    firehose_payloads = []

    monkeypatch.setattr(handler, "FIREHOSE_STREAM_NAME", "")
    monkeypatch.setattr(handler, "SNS_TOPIC_ARN", "")
    monkeypatch.setattr(
        handler,
        "_store_transaction",
        lambda transaction: stored.append(transaction),
    )
    monkeypatch.setattr(
        handler,
        "publish_to_firehose",
        lambda transaction: (
            firehose_payloads.append(transaction),
            {"published": False, "destination": "not_configured"},
        )[1],
    )

    legacy = {"transaction_id": "txn-legacy", "account_id": "acct-1"}
    explicit = {"transaction_id": "txn-bank", "account_id": "acct-2", "bank_id": "bank_x"}

    handler.process_flagged_transaction(legacy)
    handler.process_flagged_transaction(explicit)

    assert stored[0]["bank_id"] == "default"
    assert stored[1]["bank_id"] == "bank_x"
    assert firehose_payloads[0]["bank_id"] == "default"
    assert firehose_payloads[1]["bank_id"] == "bank_x"

    output = capsys.readouterr().out
    assert "bank_id=default" in output
    assert "bank_id=bank_x" in output


def test_lambda_handler_processes_sqs_batch(monkeypatch):
    processed_ids = []

    monkeypatch.setattr(handler, "_store_transaction", lambda transaction: None)
    monkeypatch.setattr(
        handler,
        "publish_to_firehose",
        lambda transaction: {"published": False, "destination": "not_configured"},
    )
    monkeypatch.setattr(
        handler,
        "publish_customer_alert",
        lambda transaction: {"sent": True, "destination": "log"},
    )

    def track_process(transaction):
        processed_ids.append(transaction["transaction_id"])
        return {
            "processed": True,
            "transaction_id": transaction["transaction_id"],
            "firehose_status": {"published": False, "destination": "not_configured"},
            "alert_status": {"sent": True, "destination": "log"},
        }

    monkeypatch.setattr(handler, "process_flagged_transaction", track_process)

    event = {
        "Records": [
            {"body": json.dumps({"transaction_id": "txn-a"})},
            {"body": json.dumps({"transaction_id": "txn-b"})},
        ]
    }

    result = handler.lambda_handler(event, context=None)

    assert result["batch_size"] == 2
    assert processed_ids == ["txn-a", "txn-b"]


def test_process_flagged_transaction_includes_firehose_status(monkeypatch):
    monkeypatch.setattr(handler, "_store_transaction", lambda transaction: None)
    monkeypatch.setattr(handler, "FIREHOSE_STREAM_NAME", "")
    monkeypatch.setattr(
        handler,
        "publish_customer_alert",
        lambda transaction: {"sent": True, "destination": "log"},
    )

    result = handler.process_flagged_transaction({"transaction_id": "txn-001"})

    assert result["firehose_status"] == {
        "published": False,
        "destination": "not_configured",
    }


def test_lambda_handler_skips_invalid_json_record():
    event = {"Records": [{"body": "not-json"}]}

    result = handler.lambda_handler(event, context=None)

    assert result["batch_size"] == 1
    assert result["results"][0]["processed"] is False
    assert "error" in result["results"][0]


def test_lambda_handler_skips_missing_body():
    event = {"Records": [{}]}

    result = handler.lambda_handler(event, context=None)

    assert result["results"][0]["processed"] is False
    assert "Missing SQS message body" in result["results"][0]["error"]


def test_publish_customer_alert_uses_sns_when_configured(monkeypatch):
    published = []

    class FakeSNSClient:
        def publish(self, **kwargs):
            published.append(kwargs)

    def fake_client(service_name, region_name=None):
        assert service_name == "sns"
        return FakeSNSClient()

    monkeypatch.setattr(handler, "SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:123:alerts")
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

    status = handler.publish_customer_alert(
        {
            "transaction_id": "txn-sns",
            "bank_id": "default",
            "account_id": "acc-1",
            "amount": 5000,
            "location": "Toronto",
            "risk_score": 50,
        }
    )

    assert status == {"sent": True, "destination": "sns"}
    assert published[0]["TopicArn"].endswith(":alerts")
    assert "txn-sns" in published[0]["Message"]


def test_store_transaction_writes_local_fallback_file(tmp_path, monkeypatch):
    fallback_file = tmp_path / "lambda_processed_alerts.jsonl"
    monkeypatch.setattr(handler, "DYNAMODB_TABLE_NAME", "")
    monkeypatch.setattr(handler, "ENVIRONMENT", "local")
    monkeypatch.setattr(handler, "LOCAL_FALLBACK_ENABLED", True)
    monkeypatch.setattr(handler, "LOCAL_FALLBACK_FILE", fallback_file)

    transaction = {"transaction_id": "txn-local", "account_id": "acc-1"}
    handler._store_transaction(transaction)

    lines = fallback_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["transaction_id"] == "txn-local"


def test_store_transaction_writes_to_dynamodb(monkeypatch):
    stored_items = []

    class FakeTable:
        def put_item(self, Item):
            stored_items.append(Item)

    class FakeDynamoResource:
        def Table(self, name):
            assert name == "fraud-table"
            return FakeTable()

    def fake_resource(service_name, region_name=None):
        assert service_name == "dynamodb"
        return FakeDynamoResource()

    monkeypatch.setattr(handler, "DYNAMODB_TABLE_NAME", "fraud-table")
    monkeypatch.setattr(handler, "ENVIRONMENT", "local")
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(resource=fake_resource))

    transaction = {
        "transaction_id": "txn-ddb",
        "amount": 100.5,
        "risk_score": 50,
    }
    handler._store_transaction(transaction)

    assert len(stored_items) == 1
    assert stored_items[0]["transaction_id"] == "txn-ddb"
    assert stored_items[0]["amount"] == Decimal("100.5")

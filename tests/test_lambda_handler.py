from decimal import Decimal
import importlib


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

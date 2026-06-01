"""Quick manual test for the Lambda handler (no AWS required).

Run it directly:

    python lambda/test_local.py

It builds a fake SQS event with two flagged transactions, invokes the handler
with the local file fallback enabled, and prints the result. Processed alerts
are appended to ``local_data/lambda_processed_alerts.jsonl``.
"""

import json
import os

# Force the local file fallback so the test runs without DynamoDB.
os.environ["DYNAMODB_TABLE_NAME"] = ""
os.environ["LOCAL_FALLBACK_ENABLED"] = "true"

from handler import lambda_handler


def _sqs_event(transactions: list[dict]) -> dict:
    """Wrap transactions in a minimal SQS-style event."""
    return {
        "Records": [
            {"body": json.dumps(transaction)} for transaction in transactions
        ]
    }


def main() -> None:
    transactions = [
        {
            "transaction_id": "txn-001",
            "account_id": "acct-123",
            "amount": 9000,
            "transaction_type": "withdrawal",
            "location": "New York",
            "reasons": ["Unusually large withdrawal amount"],
            "risk_score": 50,
        },
        {
            "transaction_id": "txn-002",
            "account_id": "acct-456",
            "amount": 200,
            "transaction_type": "transfer",
            "location": "London",
            "reasons": ["Too many failed login attempts before transaction"],
            "risk_score": 30,
        },
    ]

    event = _sqs_event(transactions)
    result = lambda_handler(event, context=None)

    print("\nHandler result:")
    print(json.dumps(result, indent=2))

    assert result["batch_size"] == 2
    assert all(item["processed"] for item in result["results"])
    assert result["results"][0]["transaction_id"] == "txn-001"
    print("\nAll assertions passed.")


if __name__ == "__main__":
    main()

"""Simulate an SQS event and invoke the Lambda handler locally.

Run it directly:

    python lambda/local_test.py

With no DynamoDB table configured the handler falls back to writing processed
alerts to ``local_data/lambda_processed_alerts.jsonl``.
"""

import json
import os

# Force the local file fallback so the test runs without DynamoDB.
os.environ["DYNAMODB_TABLE_NAME"] = ""
os.environ["SNS_TOPIC_ARN"] = ""
os.environ["LOCAL_FALLBACK_ENABLED"] = "true"

from handler import lambda_handler


def main() -> None:
    """Run the Lambda handler with one flagged transaction SQS record."""
    sample_transaction = {
        "transaction_id": "test-txn-001",
        "account_id": "ACC123",
        "amount": 7000,
        "transaction_type": "withdrawal",
        "location": "Toronto",
        "timestamp": "2026-06-01T10:05:00",
        "failed_login_attempts": 4,
        "status": "flagged",
        "reasons": [
            "Unusually large withdrawal amount",
            "Too many failed login attempts before transaction",
        ],
        "risk_score": 80,
    }

    event = {
        "Records": [
            {
                "body": json.dumps(sample_transaction),
            }
        ]
    }

    result = lambda_handler(event, context=None)
    print("Lambda result:")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

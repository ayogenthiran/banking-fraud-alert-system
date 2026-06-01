"""AWS Lambda handler that processes flagged transactions from SQS.

The Lambda is triggered by an SQS queue. Each SQS record carries a flagged
transaction (as JSON) in its ``body``. For each record we:

1. Parse the transaction.
2. Store it in DynamoDB when a table is configured.
3. Fall back to a local JSON Lines file when DynamoDB is not available and the
   local fallback is enabled (handy for running the demo without AWS).
4. Log a customer alert message.

No email/SNS is sent yet. The assignment allows "SES/SNS or log alert message",
so we simply log the alert for now.
"""

import json
import os
from pathlib import Path

# Read configuration from the environment so the same code works locally and
# in AWS. Defaults keep the local demo working with no setup.
ENVIRONMENT = os.environ.get("ENVIRONMENT", "local").lower()
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
DYNAMODB_TABLE_NAME = os.environ.get("DYNAMODB_TABLE_NAME", "")
LOCAL_FALLBACK_ENABLED = os.environ.get("LOCAL_FALLBACK_ENABLED", "true").lower() == "true"

# Directory and file used when falling back to local storage.
LOCAL_DATA_DIR = Path("local_data")
LOCAL_FALLBACK_FILE = LOCAL_DATA_DIR / "lambda_processed_alerts.jsonl"

# Partition key for the DynamoDB table.
PARTITION_KEY = "transaction_id"


def lambda_handler(event, context):
    """Entry point invoked by AWS Lambda for SQS events.

    Args:
        event: The Lambda event. For an SQS trigger this contains a list of
            records under the ``Records`` key.
        context: The Lambda context object (unused).

    Returns:
        A summary dict listing the result of each processed transaction.
    """
    results = []

    for record in event.get("Records", []):
        transaction = json.loads(record["body"])
        results.append(process_flagged_transaction(transaction))

    return {"batch_size": len(results), "results": results}


def process_flagged_transaction(transaction: dict) -> dict:
    """Store a flagged transaction and log a customer alert.

    Args:
        transaction: The flagged transaction parsed from the SQS message body.

    Returns:
        A dict describing the outcome of processing the transaction.
    """
    transaction_id = transaction.get("transaction_id", "unknown")

    _store_transaction(transaction)

    alert = "Customer alert logged for suspicious transaction"
    print(
        f"ALERT: {alert} | transaction_id={transaction_id} "
        f"account_id={transaction.get('account_id')} "
        f"amount={transaction.get('amount')} "
        f"reasons={transaction.get('reasons')}"
    )

    return {
        "processed": True,
        "transaction_id": transaction_id,
        "alert": alert,
    }


def _store_transaction(transaction: dict) -> None:
    """Persist a transaction to DynamoDB, falling back to a local file.

    Local runs can fall back to a JSONL file. In AWS, DynamoDB errors are
    raised so Lambda fails the SQS message and it can be retried.
    """
    if DYNAMODB_TABLE_NAME:
        try:
            import boto3

            dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
            table = dynamodb.Table(DYNAMODB_TABLE_NAME)
            table.put_item(Item=transaction)
            print(
                "DynamoDB write succeeded: "
                f"table={DYNAMODB_TABLE_NAME} "
                f"transaction_id={transaction.get(PARTITION_KEY, 'unknown')}"
            )
            return
        except Exception as e:  # noqa: BLE001 - keep error handling simple for the demo
            print(f"DynamoDB write failed: {e}")
            if ENVIRONMENT == "aws":
                raise

            print("Using local fallback because ENVIRONMENT is local.")

    if ENVIRONMENT == "aws":
        raise RuntimeError("DYNAMODB_TABLE_NAME must be configured when ENVIRONMENT=aws")

    if LOCAL_FALLBACK_ENABLED:
        LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
        with LOCAL_FALLBACK_FILE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(transaction) + "\n")
        print(
            "Local fallback write succeeded: "
            f"file={LOCAL_FALLBACK_FILE} "
            f"transaction_id={transaction.get(PARTITION_KEY, 'unknown')}"
        )

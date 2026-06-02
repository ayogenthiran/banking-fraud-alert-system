"""AWS Lambda handler that processes flagged transactions from SQS.

The Lambda is triggered by an SQS queue. Each SQS record carries a flagged
transaction (as JSON) in its ``body``. For each record we:

1. Parse the transaction.
2. Store it in DynamoDB when a table is configured.
3. Fall back to a local JSON Lines file when DynamoDB is not available and the
   local fallback is enabled (handy for running the demo without AWS).
4. Send a copy to Kinesis Firehose when configured for analytics.
5. Send a customer alert through SNS when configured, otherwise log it.

Local runs keep working without AWS because alerts fall back to log output.
"""

import json
import os
from decimal import Decimal
from pathlib import Path

# Read configuration from the environment so the same code works locally and
# in AWS. Defaults keep the local demo working with no setup.
ENVIRONMENT = os.environ.get("ENVIRONMENT", "local").lower()
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
DYNAMODB_TABLE_NAME = os.environ.get("DYNAMODB_TABLE_NAME", "")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")
FIREHOSE_STREAM_NAME = os.environ.get("FIREHOSE_STREAM_NAME", "")
LOCAL_FALLBACK_ENABLED = os.environ.get("LOCAL_FALLBACK_ENABLED", "true").lower() == "true"

# Directory and file used when falling back to local storage.
LOCAL_DATA_DIR = Path("local_data")
LOCAL_FALLBACK_FILE = LOCAL_DATA_DIR / "lambda_processed_alerts.jsonl"

# Partition key for the DynamoDB table.
PARTITION_KEY = "transaction_id"
DEFAULT_BANK_ID = "default"


def _resolve_bank_id(transaction: dict) -> str:
    """Return bank_id from a transaction, using DEFAULT_BANK_ID when absent or blank."""
    value = transaction.get("bank_id")
    if value is None:
        return DEFAULT_BANK_ID
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or DEFAULT_BANK_ID
    return DEFAULT_BANK_ID


def _with_resolved_bank_id(transaction: dict) -> dict:
    """Copy a transaction and ensure bank_id is set for storage and downstream alerts."""
    enriched = dict(transaction)
    enriched["bank_id"] = _resolve_bank_id(transaction)
    return enriched


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
        results.append(_process_sqs_record(record))

    return {"batch_size": len(results), "results": results}


def _process_sqs_record(record: dict) -> dict:
    """Parse one SQS record and process it, returning a safe result on bad input."""
    try:
        body = record.get("body")
        if body is None:
            raise ValueError("Missing SQS message body")

        transaction = json.loads(body)
        if not isinstance(transaction, dict):
            raise ValueError("Transaction payload must be a JSON object")

        return process_flagged_transaction(transaction)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        print(f"Skipping invalid SQS record: {exc}")
        return {
            "processed": False,
            "error": str(exc),
        }


def process_flagged_transaction(transaction: dict) -> dict:
    """Store a flagged transaction and log a customer alert.

    Args:
        transaction: The flagged transaction parsed from the SQS message body.

    Returns:
        A dict describing the outcome of processing the transaction.
    """
    transaction = _with_resolved_bank_id(transaction)
    transaction_id = transaction.get("transaction_id", "unknown")

    _store_transaction(transaction)
    firehose_status = publish_to_firehose(transaction)
    alert_status = publish_customer_alert(transaction)

    return {
        "processed": True,
        "transaction_id": transaction_id,
        "firehose_status": firehose_status,
        "alert_status": alert_status,
    }


def publish_to_firehose(transaction: dict) -> dict:
    """Send a JSON copy of the processed transaction to Firehose when enabled."""
    if not FIREHOSE_STREAM_NAME:
        return {"published": False, "destination": "not_configured"}

    try:
        import boto3

        firehose = boto3.client("firehose", region_name=AWS_REGION)
        firehose.put_record(
            DeliveryStreamName=FIREHOSE_STREAM_NAME,
            Record={
                "Data": (json.dumps(transaction, default=str) + "\n").encode("utf-8")
            },
        )
        print(
            "Firehose write succeeded: "
            f"stream={FIREHOSE_STREAM_NAME} "
            f"transaction_id={transaction.get(PARTITION_KEY, 'unknown')}"
        )
        return {"published": True, "destination": "firehose"}
    except Exception as e:  # noqa: BLE001 - keep error handling simple for the demo
        print(f"Firehose write failed: {e}")
        return {"published": False, "destination": "firehose"}


def publish_customer_alert(transaction: dict) -> dict:
    """Publish or log a customer alert for a suspicious transaction."""
    message = (
        "Suspicious transaction alert | "
        f"transaction_id={transaction.get('transaction_id', 'unknown')} "
        f"bank_id={transaction['bank_id']} "
        f"account_id={transaction.get('account_id')} "
        f"amount={transaction.get('amount')} "
        f"location={transaction.get('location')} "
        f"risk_score={transaction.get('risk_score')}"
    )

    if SNS_TOPIC_ARN:
        import boto3

        sns = boto3.client("sns", region_name=AWS_REGION)
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Message=message,
            Subject="Suspicious transaction alert",
        )
        return {"sent": True, "destination": "sns"}

    print(f"ALERT: {message}")
    return {"sent": True, "destination": "log"}


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
            table.put_item(Item=_to_dynamodb_compatible(transaction))
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


def _to_dynamodb_compatible(value):
    """Convert parsed JSON values into types accepted by DynamoDB."""
    if isinstance(value, float):
        return Decimal(str(value))

    if isinstance(value, dict):
        return {key: _to_dynamodb_compatible(item) for key, item in value.items()}

    if isinstance(value, list):
        return [_to_dynamodb_compatible(item) for item in value]

    return value

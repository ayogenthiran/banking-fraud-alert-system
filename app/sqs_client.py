"""Publish flagged transaction events to SQS, with a local file fallback.

The primary path sends events to an SQS queue. When no queue is configured and
the local fallback is enabled, events are appended to a JSON Lines file so the
demo still produces durable output without any AWS resources.
"""

import json
from pathlib import Path

from app.config import get_settings

# Directory and file used when falling back to local storage.
LOCAL_DATA_DIR = Path("local_data")
LOCAL_FALLBACK_FILE = LOCAL_DATA_DIR / "flagged_transactions.jsonl"


def publish_flagged_transaction(event: dict) -> dict:
    """Publish a flagged transaction event.

    Sends the event to SQS when a queue URL is configured. Otherwise, when the
    local fallback is enabled, appends the event as one JSON line to
    ``local_data/flagged_transactions.jsonl``. If neither destination is
    available, the event is not published.

    Args:
        event: The flagged transaction event to publish.

    Returns:
        A dict describing the outcome, e.g.
        ``{"published": True, "destination": "sqs"}``.
    """
    settings = get_settings()

    try:
        if settings.sqs_queue_url:
            import boto3

            client = boto3.client("sqs", region_name=settings.aws_region)
            client.send_message(
                QueueUrl=settings.sqs_queue_url,
                MessageBody=json.dumps(event),
            )
            return {"published": True, "destination": "sqs"}

        if settings.local_fallback_enabled:
            LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
            with LOCAL_FALLBACK_FILE.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event) + "\n")
            return {"published": True, "destination": "local"}

        if settings.environment.lower() == "aws":
            raise RuntimeError("SQS_QUEUE_URL must be configured when ENVIRONMENT=aws")

        return {"published": False, "destination": "none"}
    except Exception as e:  # noqa: BLE001 - keep error handling simple for the demo
        if settings.environment.lower() == "aws":
            raise

        return {"published": False, "destination": "error", "error": str(e)}

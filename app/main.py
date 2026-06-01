from uuid import uuid4

from fastapi import FastAPI

from app.config import get_settings
from app.fraud_rules import evaluate_transaction
from app.models import FraudStatus, TransactionRequest, TransactionResponse
from app.sqs_client import publish_flagged_transaction

settings = get_settings()

app = FastAPI(title="Banking Fraud Detection API")

APPROVED_MESSAGE = "Transaction approved"
FLAGGED_MESSAGE = "Transaction flagged for review"


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "environment": settings.environment,
        "status": "ok",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "healthy",
        "service": settings.app_name,
    }


@app.post(
    "/transactions",
    response_model=TransactionResponse,
    summary="Process a transaction",
    description=(
        "Evaluate an incoming transaction against the fraud rules and return "
        "the resulting decision. Approved transactions are safe to process, "
        "while flagged transactions are held for manual review."
    ),
    tags=["transactions"],
)
def process_transaction(transaction: TransactionRequest) -> TransactionResponse:
    transaction_id = str(uuid4())
    decision = evaluate_transaction(transaction)

    notification_status = None
    if decision.status == FraudStatus.APPROVED:
        message = APPROVED_MESSAGE
    else:
        message = FLAGGED_MESSAGE
        event = {
            "transaction_id": transaction_id,
            "account_id": transaction.account_id,
            "amount": transaction.amount,
            "transaction_type": transaction.transaction_type,
            "location": transaction.location,
            "timestamp": transaction.timestamp.isoformat(),
            "failed_login_attempts": transaction.failed_login_attempts,
            "status": decision.status,
            "reasons": decision.reasons,
            "risk_score": decision.risk_score,
        }
        notification_status = publish_flagged_transaction(event)

    return TransactionResponse(
        transaction_id=transaction_id,
        account_id=transaction.account_id,
        status=decision.status,
        reasons=decision.reasons,
        risk_score=decision.risk_score,
        message=message,
        notification_status=notification_status,
    )

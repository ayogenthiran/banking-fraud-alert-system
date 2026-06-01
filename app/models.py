from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class TransactionType(StrEnum):
    WITHDRAWAL = "withdrawal"
    DEPOSIT = "deposit"
    TRANSFER = "transfer"


class FraudStatus(StrEnum):
    APPROVED = "approved"
    FLAGGED = "flagged"


class TransactionRequest(BaseModel):
    account_id: str
    amount: float = Field(gt=0)
    transaction_type: TransactionType
    location: str
    timestamp: datetime
    failed_login_attempts: int = Field(default=0, ge=0)


class FraudDecision(BaseModel):
    status: FraudStatus
    reasons: list[str]
    risk_score: int


class TransactionResponse(BaseModel):
    transaction_id: str
    account_id: str
    status: FraudStatus
    reasons: list[str]
    risk_score: int
    message: str
    notification_status: dict | None = None

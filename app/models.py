from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class TransactionType(str, Enum):
    WITHDRAWAL = "withdrawal"
    DEPOSIT = "deposit"
    TRANSFER = "transfer"


class FraudStatus(str, Enum):
    APPROVED = "approved"
    FLAGGED = "flagged"


class TransactionRequest(BaseModel):
    account_id: str
    bank_id: str | None = Field(
        default="default",
        description="Bank or tenant identifier used to select fraud thresholds.",
    )
    amount: float = Field(gt=0)
    transaction_type: TransactionType
    location: str
    timestamp: datetime
    failed_login_attempts: int = Field(default=0, ge=0)

    @field_validator("bank_id", mode="before")
    @classmethod
    def normalize_bank_id(cls, value: str | None) -> str:
        if value is None:
            return "default"
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or "default"
        return "default"


class FraudDecision(BaseModel):
    status: FraudStatus
    reasons: list[str]
    risk_score: int


class TransactionResponse(BaseModel):
    transaction_id: str
    account_id: str
    bank_id: str
    status: FraudStatus
    reasons: list[str]
    risk_score: int
    message: str
    notification_status: Optional[dict] = None

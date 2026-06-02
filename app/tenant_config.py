from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel


class FraudThresholds(BaseModel):
    large_withdrawal_threshold: float
    failed_login_threshold: int
    location_window_minutes: int


THRESHOLDS_CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "bank_thresholds.json"
)


@lru_cache
def _load_bank_thresholds() -> dict[str, FraudThresholds]:
    """Load tenant thresholds once for the lifetime of the process."""
    with THRESHOLDS_CONFIG_PATH.open(encoding="utf-8") as config_file:
        raw_thresholds = json.load(config_file)

    return {
        bank_id: FraudThresholds.model_validate(thresholds)
        for bank_id, thresholds in raw_thresholds.items()
    }


def get_thresholds_for_bank(bank_id: str | None) -> FraudThresholds:
    """Return thresholds for a bank, falling back to the default tenant."""
    thresholds_by_bank = _load_bank_thresholds()
    normalized_bank_id = bank_id.strip() if bank_id else None

    # This file-backed config keeps the assignment simple. In production, these
    # tenant settings could come from DynamoDB or AWS Systems Manager Parameter Store.
    return thresholds_by_bank.get(
        normalized_bank_id,
        thresholds_by_bank["default"],
    )

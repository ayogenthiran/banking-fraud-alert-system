"""Simple, rule-based fraud detection for the local demo.

This module exposes a single entry point, :func:`evaluate_transaction`, which
applies a handful of easy-to-explain rules to an incoming transaction and
returns a :class:`FraudDecision`.

The rules are intentionally simple so they are easy to reason about during a
demo. State (recent account locations) is kept in a plain in-memory dictionary,
which is fine for a single-process local run but is NOT suitable for production.
"""

from datetime import datetime, timedelta

from app.models import (
    FraudDecision,
    FraudStatus,
    TransactionRequest,
    TransactionType,
)

# Threshold above which a withdrawal is considered unusually large.
LARGE_WITHDRAWAL_THRESHOLD = 5000

# Number of failed logins before a transaction that we treat as suspicious.
FAILED_LOGIN_THRESHOLD = 3

# Time window used when comparing the current location to the previous one.
LOCATION_WINDOW = timedelta(minutes=10)

# Risk score contributions for each rule.
RISK_LARGE_WITHDRAWAL = 50
RISK_FAILED_LOGINS = 30
RISK_DIFFERENT_LOCATION = 40

# In-memory store mapping account_id -> (last_location, last_timestamp).
# This is module-level state shared across requests. It works for a local,
# single-process demo but would need a real datastore (e.g. Redis) in prod.
RECENT_ACCOUNT_LOCATIONS: dict[str, tuple[str, datetime]] = {}


def evaluate_transaction(transaction: TransactionRequest) -> FraudDecision:
    """Evaluate a single transaction against the fraud rules.

    Args:
        transaction: The incoming transaction to score.

    Returns:
        A :class:`FraudDecision` containing the overall status, the list of
        human-readable reasons for any flags, and the computed risk score.
    """
    reasons: list[str] = []
    risk_score = 0

    # Rule 1: Unusually large withdrawal.
    if (
        transaction.transaction_type == TransactionType.WITHDRAWAL
        and transaction.amount >= LARGE_WITHDRAWAL_THRESHOLD
    ):
        reasons.append("Unusually large withdrawal amount")
        risk_score += RISK_LARGE_WITHDRAWAL

    # Rule 2: Too many failed login attempts before the transaction.
    if transaction.failed_login_attempts >= FAILED_LOGIN_THRESHOLD:
        reasons.append("Too many failed login attempts before transaction")
        risk_score += RISK_FAILED_LOGINS

    # Rule 3: Different geographic region within a short time window.
    if _is_location_change_suspicious(transaction):
        reasons.append(
            "Transaction from different geographic region within short time window"
        )
        risk_score += RISK_DIFFERENT_LOCATION

    # Remember this transaction's location so future transactions can compare.
    RECENT_ACCOUNT_LOCATIONS[transaction.account_id] = (
        transaction.location,
        transaction.timestamp,
    )

    # Any positive risk score means the transaction is flagged for review.
    status = FraudStatus.FLAGGED if risk_score > 0 else FraudStatus.APPROVED

    return FraudDecision(status=status, reasons=reasons, risk_score=risk_score)


def _is_location_change_suspicious(transaction: TransactionRequest) -> bool:
    """Return True if the account moved to a new location within the window.

    We look up the account's previous location and timestamp. If the previous
    location differs from the current one and both happened within
    :data:`LOCATION_WINDOW`, we consider it suspicious.
    """
    previous = RECENT_ACCOUNT_LOCATIONS.get(transaction.account_id)
    if previous is None:
        # No prior activity for this account, so nothing to compare against.
        return False

    last_location, last_timestamp = previous

    # Same place is never suspicious, regardless of timing.
    if last_location == transaction.location:
        return False

    # Different place: only suspicious if it happened within the time window.
    time_difference = abs(transaction.timestamp - last_timestamp)
    return time_difference <= LOCATION_WINDOW

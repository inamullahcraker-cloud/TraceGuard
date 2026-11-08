
"""Core domain models for the TraceGuard investigation system."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class OrderStatus(str, Enum):
    """Supported financial reconciliation statuses."""

    PAID = "PAID"
    UNPAID = "UNPAID"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    REFUNDED = "REFUNDED"
    DISPUTED = "DISPUTED"
    UNKNOWN = "UNKNOWN"


class Confidence(str, Enum):
    """Confidence levels assigned to investigation results."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass(frozen=True, slots=True)
class Event:
    """Represent a validated event from an external service."""

    tenant_id: str
    order_id: str
    event_id: str
    source: str
    event_type: str
    occurred_at: datetime
    ingested_at: datetime

    attempt_id: str | None = None
    capture_id: str | None = None
    refund_id: str | None = None
    amount_cents: int | None = None
    currency: str | None = None
    text: str | None = None

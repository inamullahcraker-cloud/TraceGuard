
"""Validation utilities for TraceGuard financial events."""

import re
from datetime import datetime
from typing import Any

from traceguard.exceptions import EventValidationError
from traceguard.models import Event


SUPPORTED_EVENT_TYPES = {
    "ORDER_CREATED",
    "PAYMENT_FAILED",
    "PAYMENT_CAPTURED",
    "REFUND_ISSUED",
    "CHARGEBACK_OPENED",
    "NOTE",
}

EXPECTED_SOURCES = {
    "ORDER_CREATED": "checkout",
    "PAYMENT_FAILED": "payments",
    "PAYMENT_CAPTURED": "payments",
    "REFUND_ISSUED": "payments",
    "CHARGEBACK_OPENED": "payments",
    "NOTE": "support",
}

FINANCIAL_AMOUNT_TYPES = {
    "ORDER_CREATED",
    "PAYMENT_CAPTURED",
    "REFUND_ISSUED",
}


def _required_string(record: dict[str, Any], field: str) -> str:
    """Validate and return a required non-empty string."""
    value = record.get(field)

    if not isinstance(value, str) or not value.strip():
        raise EventValidationError(
            f"Missing or invalid required field: {field}"
        )

    return value.strip()


def _parse_timestamp(value: Any, field: str) -> datetime:
    """Parse a timezone-aware ISO 8601 timestamp."""
    if not isinstance(value, str) or not value.strip():
        raise EventValidationError(
            f"Missing or invalid timestamp: {field}"
        )

    try:
        timestamp = datetime.fromisoformat(
            value.strip().replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise EventValidationError(
            f"Invalid ISO 8601 timestamp: {field}"
        ) from exc

    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise EventValidationError(
            f"Timestamp must include timezone information: {field}"
        )

    return timestamp


def _validate_amount(record: dict[str, Any]) -> int:
    """Validate a positive integer financial amount."""
    amount = record.get("amount_cents")

    if isinstance(amount, bool) or not isinstance(amount, int):
        raise EventValidationError(
            "amount_cents must be an integer."
        )

    if amount <= 0:
        raise EventValidationError(
            "amount_cents must be greater than zero."
        )

    return amount


def _validate_currency(record: dict[str, Any]) -> str:
    """Validate a three-letter uppercase currency code."""
    currency = record.get("currency")

    if not isinstance(currency, str):
        raise EventValidationError("Currency is required.")

    currency = currency.strip()

    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise EventValidationError(
            f"Invalid currency code: {currency}"
        )

    return currency


def validate_event(record: dict[str, Any]) -> Event:
    """Validate a raw JSON event and create an Event object.

    Args:
        record: Raw event dictionary from the JSONL loader.

    Returns:
        A validated Event instance.

    Raises:
        EventValidationError: If the event violates validation rules.
    """
    if not isinstance(record, dict):
        raise EventValidationError("Event must be a dictionary.")

    tenant_id = _required_string(record, "tenant_id")
    order_id = _required_string(record, "order_id")
    event_id = _required_string(record, "event_id")
    source = _required_string(record, "source")
    event_type = _required_string(record, "type")

    if event_type not in SUPPORTED_EVENT_TYPES:
        raise EventValidationError(
            f"Unsupported event type: {event_type}"
        )

    expected_source = EXPECTED_SOURCES[event_type]

    if source != expected_source:
        raise EventValidationError(
            f"{event_type} must come from {expected_source}."
        )

    occurred_at = _parse_timestamp(
        record.get("occurred_at"), "occurred_at"
    )

    ingested_at = _parse_timestamp(
        record.get("ingested_at"), "ingested_at"
    )

    amount_cents = None
    currency = None

    if event_type in FINANCIAL_AMOUNT_TYPES:
        amount_cents = _validate_amount(record)
        currency = _validate_currency(record)

    capture_id = record.get("capture_id")
    refund_id = record.get("refund_id")
    attempt_id = record.get("attempt_id")
    text = record.get("text")

    if event_type in {"PAYMENT_CAPTURED", "REFUND_ISSUED",
                      "CHARGEBACK_OPENED"}:
        if not isinstance(capture_id, str) or not capture_id.strip():
            raise EventValidationError(
                f"{event_type} requires capture_id."
            )
        capture_id = capture_id.strip()

    if event_type == "REFUND_ISSUED":
        if not isinstance(refund_id, str) or not refund_id.strip():
            raise EventValidationError(
                "REFUND_ISSUED requires refund_id."
            )
        refund_id = refund_id.strip()

    if attempt_id is not None:
        if not isinstance(attempt_id, str) or not attempt_id.strip():
            raise EventValidationError("Invalid attempt_id.")
        attempt_id = attempt_id.strip()

    if text is not None and not isinstance(text, str):
        raise EventValidationError("Event text must be a string.")

    return Event(
        tenant_id=tenant_id,
        order_id=order_id,
        event_id=event_id,
        source=source,
        event_type=event_type,
        occurred_at=occurred_at,
        ingested_at=ingested_at,
        attempt_id=attempt_id,
        capture_id=capture_id,
        refund_id=refund_id,
        amount_cents=amount_cents,
        currency=currency,
        text=text,
    )

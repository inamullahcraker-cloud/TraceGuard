
"""Event deduplication and transaction identity checks."""

from traceguard.exceptions import IntegrityError
from traceguard.models import Event


def _event_identity(event: Event) -> tuple[str, str]:
    """Return the tenant-scoped event identity."""
    return event.tenant_id, event.event_id


def _substantive_event_data(event: Event) -> tuple:
    """Return event fields excluding ingestion timestamp."""
    return (
        event.tenant_id,
        event.order_id,
        event.event_id,
        event.source,
        event.event_type,
        event.occurred_at,
        event.attempt_id,
        event.capture_id,
        event.refund_id,
        event.amount_cents,
        event.currency,
        event.text,
    )


def deduplicate_events(events: list[Event]) -> list[Event]:
    """Remove identical duplicate events.

    Raises:
        IntegrityError: If an event identity has conflicting data.
    """
    unique_events: dict[tuple[str, str], Event] = {}

    for event in events:
        identity = _event_identity(event)
        existing = unique_events.get(identity)

        if existing is None:
            unique_events[identity] = event
            continue

        if (
            _substantive_event_data(existing)
            != _substantive_event_data(event)
        ):
            raise IntegrityError(
                f"Conflicting event identity: {identity}"
            )

        # Identical duplicate: retain the first record.

    return list(unique_events.values())



def validate_transaction_identities(events: list[Event]) -> None:
    """Reject conflicting capture and refund transaction identities.

    Transaction IDs are unique within a tenant and transaction type.
    Identical transaction records may have different event IDs, but
    conflicting financial data must raise IntegrityError.
    """
    transactions: dict[tuple[str, str, str], tuple] = {}

    for event in events:
        if event.event_type == "PAYMENT_CAPTURED":
            transaction_type = "capture"
            transaction_id = event.capture_id

        elif event.event_type == "REFUND_ISSUED":
            transaction_type = "refund"
            transaction_id = event.refund_id

        else:
            continue

        if transaction_id is None:
            raise IntegrityError(
                f"Missing {transaction_type} transaction ID "
                f"for event {event.event_id}"
            )

        # Do not include order_id in the identity key.
        identity = (
            event.tenant_id,
            transaction_type,
            transaction_id,
        )

        # Include order_id in the data being compared.
        substantive_data = (
            event.order_id,
            event.capture_id,
            event.refund_id,
            event.amount_cents,
            event.currency,
            event.event_type,
        )

        existing = transactions.get(identity)

        if existing is not None and existing != substantive_data:
            raise IntegrityError(
                f"Conflicting {transaction_type} transaction ID: "
                f"{transaction_id}"
            )

        transactions[identity] = substantive_data

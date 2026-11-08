
"""Deterministic financial reconciliation for TraceGuard orders."""

from dataclasses import dataclass

from traceguard.deduplicator import (
    deduplicate_events,
    validate_transaction_identities,
)
from traceguard.exceptions import IntegrityError
from traceguard.models import Confidence, Event, OrderStatus


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    """Immutable result of an order financial reconciliation."""

    status: OrderStatus
    captured_cents: int | None
    refunded_cents: int | None
    net_paid_cents: int | None
    anomalies: tuple[str, ...]
    evidence_event_ids: tuple[str, ...]
    explanation: str
    confidence: Confidence


def _unknown_result(
    anomalies: list[str],
    evidence_ids: list[str],
    explanation: str,
) -> ReconciliationResult:
    """Build an UNKNOWN result when financial evidence is unreliable."""
    return ReconciliationResult(
        status=OrderStatus.UNKNOWN,
        captured_cents=None,
        refunded_cents=None,
        net_paid_cents=None,
        anomalies=tuple(anomalies),
        evidence_event_ids=tuple(sorted(set(evidence_ids))),
        explanation=explanation,
        confidence=Confidence.LOW,
    )


def reconcile_order(
    events: list[Event],
    tenant_id: str,
    order_id: str,
) -> ReconciliationResult:
    """Reconcile one order using validated financial events.

    Events belonging to other tenants are never considered.

    Raises no integrity exceptions for ordinary data contradictions:
    those contradictions produce an UNKNOWN result with anomalies.
    """
    if not tenant_id.strip() or not order_id.strip():
        raise ValueError("tenant_id and order_id must be non-empty.")

    # Isolate the tenant before examining event identities.
    tenant_events = [
        event for event in events
        if event.tenant_id == tenant_id
    ]

    target_events: list[Event] = [
        event for event in tenant_events
        if event.order_id == order_id
    ]

    if not target_events:
        return _unknown_result(
            ["No events found for the requested tenant and order."],
            [],
            "The order cannot be reconciled because no evidence was found.",
        )

    evidence_ids = [event.event_id for event in target_events]

    # Event IDs are unique within a tenant, not within an order.
    try:
        unique_tenant_events = deduplicate_events(tenant_events)

        target_events = [
            event for event in unique_tenant_events
            if event.order_id == order_id
        ]

        evidence_ids = [event.event_id for event in target_events]

        # Check transaction IDs that appear in this order, including
        # possible reuse by another order belonging to the same tenant.
        target_capture_ids = {
            event.capture_id for event in target_events
            if event.event_type == "PAYMENT_CAPTURED"
        }
        target_refund_ids = {
            event.refund_id for event in target_events
            if event.event_type == "REFUND_ISSUED"
        }

        related_transactions = [
            event for event in unique_tenant_events
            if (
                event.capture_id in target_capture_ids
                and event.capture_id is not None
            ) or (
                event.refund_id in target_refund_ids
                and event.refund_id is not None
            )
        ]

        validate_transaction_identities(related_transactions)

    except IntegrityError as exc:
        return _unknown_result(
            [str(exc)],
            evidence_ids,
            "Financial integrity checks failed. Reliable totals cannot "
            "be established.",
        )

    # Establish the expected order amount and currency.
    order_definitions = [
        event for event in target_events
        if event.event_type == "ORDER_CREATED"
    ]

    if not order_definitions:
        return _unknown_result(
            ["Missing ORDER_CREATED evidence."],
            evidence_ids,
            "The expected order amount and currency are unknown.",
        )

    order_values = {
        (event.amount_cents, event.currency)
        for event in order_definitions
    }

    if len(order_values) != 1:
        return _unknown_result(
            ["Contradictory order amount or currency definitions."],
            evidence_ids,
            "Multiple conflicting order definitions were found.",
        )

    expected_cents, expected_currency = next(iter(order_values))

    # Index unique captures by their financial transaction IDs.
    captures: dict[str, Event] = {}

    for event in target_events:
        if event.event_type != "PAYMENT_CAPTURED":
            continue

        assert event.capture_id is not None

        captures.setdefault(event.capture_id, event)

    # Every refund must reference a known capture.
    refunds: dict[str, Event] = {}

    for event in target_events:
        if event.event_type != "REFUND_ISSUED":
            continue

        assert event.refund_id is not None
        assert event.capture_id is not None

        if event.capture_id not in captures:
            return _unknown_result(
                [
                    f"Refund {event.refund_id} references missing "
                    f"capture {event.capture_id}."
                ],
                evidence_ids,
                "A refund references a capture that cannot be verified.",
            )

        refunds.setdefault(event.refund_id, event)

    # Check financial currencies.
    for event in [*captures.values(), *refunds.values()]:
        if event.currency != expected_currency:
            return _unknown_result(
                [
                    f"Currency mismatch in event {event.event_id}: "
                    f"expected {expected_currency}, got {event.currency}."
                ],
                evidence_ids,
                "Financial events contain inconsistent currencies.",
            )

    # Calculate captured amount.
    captured_cents = sum(
        event.amount_cents for event in captures.values()
        if event.amount_cents is not None
    )

    if captured_cents > expected_cents:
        return _unknown_result(
            ["Total captured amount exceeds the expected order amount."],
            evidence_ids,
            "Over-capture detected. Financial totals are unreliable.",
        )

    # Calculate refunds per capture.
    refunded_by_capture: dict[str, int] = {}

    for event in refunds.values():
        assert event.capture_id is not None
        assert event.amount_cents is not None

        refunded_by_capture[event.capture_id] = (
            refunded_by_capture.get(event.capture_id, 0)
            + event.amount_cents
        )

    for capture_id, refunded_amount in refunded_by_capture.items():
        capture_amount = captures[capture_id].amount_cents

        assert capture_amount is not None

        if refunded_amount > capture_amount:
            return _unknown_result(
                [
                    f"Refunds exceed capture amount for {capture_id}."
                ],
                evidence_ids,
                "An over-refund was detected.",
            )

    refunded_cents = sum(refunded_by_capture.values())
    net_paid_cents = captured_cents - refunded_cents

    # A chargeback must reference a verified capture.
    chargebacks = [
        event for event in target_events
        if event.event_type == "CHARGEBACK_OPENED"
    ]

    for event in chargebacks:
        if event.capture_id not in captures:
            return _unknown_result(
                [
                    f"Chargeback {event.event_id} references a "
                    f"missing capture."
                ],
                evidence_ids,
                "Chargeback evidence cannot be linked to a verified capture.",
            )

    # Determine the status using explicit precedence.
    if chargebacks:
        status = OrderStatus.DISPUTED
        explanation = (
            "A valid open chargeback exists for a verified payment capture."
        )

    elif captured_cents == 0:
        failures = [
            event for event in target_events
            if event.event_type == "PAYMENT_FAILED"
        ]

        if failures:
            status = OrderStatus.UNPAID
            explanation = (
                "No successful captures were found, and a payment "
                "failure is recorded."
            )
        else:
            return _unknown_result(
                ["No successful capture or verified payment failure."],
                evidence_ids,
                "The available evidence cannot establish the payment status.",
            )

    elif refunded_cents == captured_cents:
        status = OrderStatus.REFUNDED
        explanation = "All captured funds have been refunded."

    elif refunded_cents > 0:
        status = OrderStatus.PARTIALLY_REFUNDED
        explanation = "Some, but not all, captured funds have been refunded."

    elif captured_cents == expected_cents:
        status = OrderStatus.PAID
        explanation = "Successful captures equal the expected order amount."

    else:
        status = OrderStatus.PARTIALLY_PAID
        explanation = (
            "Successful captures are below the expected order amount."
        )

    return ReconciliationResult(
        status=status,
        captured_cents=captured_cents,
        refunded_cents=refunded_cents,
        net_paid_cents=net_paid_cents,
        anomalies=(),
        evidence_event_ids=tuple(sorted(set(evidence_ids))),
        explanation=explanation,
        confidence=Confidence.HIGH,
    )

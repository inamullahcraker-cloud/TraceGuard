"""Orchestration layer for TraceGuard investigations."""

import logging
from dataclasses import dataclass, replace
from typing import Callable

from traceguard.exceptions import EventValidationError
from traceguard.investigation import InvestigationTools
from traceguard.models import Confidence, Event, OrderStatus
from traceguard.reconciliation import ReconciliationResult, reconcile_order
from traceguard.validator import validate_event

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class InvestigationReport:
    """Financial findings and contextual evidence for an investigation."""

    reconciliation: ReconciliationResult
    support_notes: tuple[str, ...]
    tool_failures: tuple[str, ...]


def _unknown_result(
    anomalies: list[str],
    evidence_ids: list[str],
    explanation: str,
) -> ReconciliationResult:
    """Build a conservative result when reliable reconciliation is impossible."""
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


def _fetch_with_retry(
    operation: Callable[[], list[dict[str, object]]],
    operation_name: str,
    max_retries: int,
) -> tuple[list[dict[str, object]] | None, str | None]:
    """Execute a retrieval operation with a bounded retry policy."""
    for attempt in range(max_retries + 1):
        try:
            records = operation()

            if not isinstance(records, list):
                raise TypeError("Tool response must be a list.")

            if not all(isinstance(record, dict) for record in records):
                raise TypeError("Every tool record must be a dictionary.")

            return records, None

        except Exception as exc:
            logger.warning(
                "%s failed on attempt %d/%d: %s",
                operation_name,
                attempt + 1,
                max_retries + 1,
                exc,
            )

            if attempt == max_retries:
                return None, (
                    f"{operation_name} failed after "
                    f"{max_retries + 1} attempts: {exc}"
                )

    return None, f"{operation_name} failed unexpectedly."


def investigate_order(
    tools: InvestigationTools,
    tenant_id: str,
    order_id: str,
    max_retries: int = 1,
) -> InvestigationReport:
    """Retrieve evidence and produce a deterministic order investigation.

    Checkout and payment evidence are essential. Support notes are optional
    context and never influence financial reconciliation.

    Args:
        tools: Evidence retrieval implementation.
        tenant_id: Tenant whose order is being investigated.
        order_id: Order identifier within that tenant.
        max_retries: Number of additional attempts after a failed tool call.

    Returns:
        InvestigationReport containing reconciliation and support context.

    Raises:
        ValueError: If the identifiers or retry count are invalid.
    """
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError("tenant_id must be a non-empty string.")

    if not isinstance(order_id, str) or not order_id.strip():
        raise ValueError("order_id must be a non-empty string.")

    if isinstance(max_retries, bool) or not isinstance(max_retries, int):
        raise ValueError("max_retries must be a non-negative integer.")

    if max_retries < 0:
        raise ValueError("max_retries must be a non-negative integer.")

    retrievals = (
        (
            "checkout",
            lambda: tools.get_order(tenant_id, order_id),
        ),
        (
            "payments",
            lambda: tools.get_payment_events(tenant_id, order_id),
        ),
        (
            "support",
            lambda: tools.get_support_notes(tenant_id, order_id),
        ),
        (
            "tenant_events",
            lambda: tools.get_tenant_events(tenant_id),
        ),
    )

    retrieved: dict[str, list[dict[str, object]]] = {}
    tool_failures: list[str] = []

    for source, operation in retrievals:
        records, failure = _fetch_with_retry(
            operation=operation,
            operation_name=f"{source} retrieval",
            max_retries=max_retries,
        )

        if failure:
            tool_failures.append(failure)
        else:
            retrieved[source] = records or []

    # Financial retrieval failures make a reliable status impossible.
    financial_failures = [
        failure
        for failure in tool_failures
        if any(
            source in failure
            for source in (
                "checkout retrieval",
                "payments retrieval",
                "tenant_events retrieval",
            )
        )
    ]

    if financial_failures:
        result = _unknown_result(
            anomalies=financial_failures,
            evidence_ids=[],
            explanation=(
                "Financial evidence retrieval failed. "
                "The order status cannot be established reliably."
            ),
        )
        return InvestigationReport(
            reconciliation=result,
            support_notes=(),
            tool_failures=tuple(tool_failures),
        )

    financial_records = retrieved["checkout"] + retrieved["payments"]
    valid_events: list[Event] = []
    evidence_ids: list[str] = []
    anomalies: list[str] = []

    expected_sources = {
        "checkout": retrieved["checkout"],
        "payments": retrieved["payments"],
    }

    # Reject records outside the requested tenant/order/source boundary.
    for expected_source, records in expected_sources.items():
        for record in records:
            event_id = record.get("event_id")
            if isinstance(event_id, str):
                evidence_ids.append(event_id)

            if (
                record.get("tenant_id") != tenant_id
                or record.get("order_id") != order_id
                or record.get("source") != expected_source
            ):
                anomalies.append(
                    f"Unexpected {expected_source} record scope or source: "
                    f"{event_id!r}"
                )
                continue

            try:
                valid_events.append(validate_event(record))
            except (EventValidationError, ValueError, TypeError) as exc:
                anomalies.append(
                    f"Invalid {expected_source} event {event_id!r}: {exc}"
                )

    # Invalid financial evidence must never be silently discarded.
    if anomalies:
        result = _unknown_result(
            anomalies=anomalies,
            evidence_ids=evidence_ids,
            explanation=(
                "Financial evidence contains invalid or out-of-scope records. "
                "A reliable order status cannot be established."
            ),
        )
        return InvestigationReport(
            reconciliation=result,
            support_notes=(),
            tool_failures=tuple(tool_failures),
        )

    # Identify transaction and event identities belonging to this order.
    target_event_ids = {event.event_id for event in valid_events}

    target_capture_ids = {
        event.capture_id
        for event in valid_events
        if event.capture_id is not None
    }

    target_refund_ids = {
        event.refund_id
        for event in valid_events
        if event.refund_id is not None
    }

    # Retrieve related records from the tenant-wide evidence index.
    # Unrelated orders are not included in the reconciliation input.
    for record in retrieved["tenant_events"]:
        if record.get("tenant_id") != tenant_id:
            continue

        is_related = (
            record.get("event_id") in target_event_ids
            or (
                record.get("capture_id") is not None
                and record.get("capture_id") in target_capture_ids
            )
            or (
                record.get("refund_id") is not None
                and record.get("refund_id") in target_refund_ids
            )
        )

        if not is_related:
            continue

        try:
            related_event = validate_event(record)
            valid_events.append(related_event)
        except (EventValidationError, ValueError, TypeError) as exc:
            anomalies.append(
                f"Invalid related tenant event "
                f"{record.get('event_id')!r}: {exc}"
            )

    if anomalies:
        result = _unknown_result(
            anomalies=anomalies,
            evidence_ids=evidence_ids,
            explanation=(
                "Related tenant evidence contains invalid records. "
                "A reliable order status cannot be established."
            ),
        )
        return InvestigationReport(
            reconciliation=result,
            support_notes=(),
            tool_failures=tuple(tool_failures),
        )

    result = reconcile_order(
        events=valid_events,
        tenant_id=tenant_id,
        order_id=order_id,
    )

    # Support records are contextual only. They are never sent to reconciliation.
    support_notes: list[str] = []

    if "support" in retrieved:
        for record in retrieved["support"]:
            if (
                record.get("tenant_id") != tenant_id
                or record.get("order_id") != order_id
                or record.get("source") != "support"
                or record.get("type") != "NOTE"
            ):
                logger.warning("Ignoring out-of-scope support record.")
                continue

            note = record.get("text")
            if isinstance(note, str) and note.strip():
                support_notes.append(note.strip())

    # Missing optional context lowers confidence but does not invalidate
    # independently established financial evidence.
    if tool_failures:
        result = replace(
            result,
            anomalies=result.anomalies + tuple(tool_failures),
            confidence=(
                Confidence.MEDIUM
                if result.confidence == Confidence.HIGH
                else result.confidence
            ),
            explanation=(
                result.explanation
                + " Support context was unavailable after bounded retries."
            ),
        )

    logger.info(
        "Investigation completed for tenant=%s order=%s status=%s",
        tenant_id,
        order_id,
        result.status.value,
    )

    return InvestigationReport(
        reconciliation=result,
        support_notes=tuple(support_notes),
        tool_failures=tuple(tool_failures),
    )
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given, settings, strategies as st

from traceguard.models import Confidence, Event, OrderStatus
from traceguard.reconciliation import reconcile_order


NOW = datetime(2026, 11, 8, 10, 0, tzinfo=timezone.utc)
TENANT = "T1"
ORDER_ID = "O-201"
EXPECTED_AMOUNT = 12900


def make_event(
    event_id: str,
    event_type: str,
    amount: int | None = None,
    currency: str | None = None,
    capture_id: str | None = None,
    refund_id: str | None = None,
    tenant_id: str = TENANT,
    order_id: str = ORDER_ID,
) -> Event:
    """Create a test event with consistent default fields."""
    return Event(
        tenant_id=tenant_id,
        order_id=order_id,
        event_id=event_id,
        source=(
            "checkout" if event_type == "ORDER_CREATED"
            else "payments"
        ),
        event_type=event_type,
        occurred_at=NOW,
        ingested_at=NOW,
        capture_id=capture_id,
        refund_id=refund_id,
        amount_cents=amount,
        currency=currency,
    )


def make_order(
    amount: int = EXPECTED_AMOUNT,
    tenant_id: str = TENANT,
    order_id: str = ORDER_ID,
) -> Event:
    return make_event(
        "order-1",
        "ORDER_CREATED",
        amount=amount,
        currency="USD",
        tenant_id=tenant_id,
        order_id=order_id,
    )


def make_capture(
    amount: int = EXPECTED_AMOUNT,
    capture_id: str = "CAP-001",
    event_id: str = "pay-1",
    tenant_id: str = TENANT,
    order_id: str = ORDER_ID,
    currency: str = "USD",
) -> Event:
    return make_event(
        event_id,
        "PAYMENT_CAPTURED",
        amount=amount,
        currency=currency,
        capture_id=capture_id,
        tenant_id=tenant_id,
        order_id=order_id,
    )


def make_refund(
    amount: int,
    capture_id: str = "CAP-001",
    refund_id: str = "REF-001",
    event_id: str = "refund-1",
) -> Event:
    return make_event(
        event_id,
        "REFUND_ISSUED",
        amount=amount,
        currency="USD",
        capture_id=capture_id,
        refund_id=refund_id,
    )


def investigate(events: list[Event]):
    return reconcile_order(events, TENANT, ORDER_ID)


# ---------------------------------------------------------
# Normal financial scenarios
# ---------------------------------------------------------

def test_fully_paid_order():
    result = investigate([
        make_order(),
        make_capture(),
    ])

    assert result.status == OrderStatus.PAID
    assert result.captured_cents == 12900
    assert result.refunded_cents == 0
    assert result.net_paid_cents == 12900
    assert result.confidence == Confidence.HIGH


def test_partially_paid_order():
    result = investigate([
        make_order(),
        make_capture(amount=5000),
    ])

    assert result.status == OrderStatus.PARTIALLY_PAID
    assert result.captured_cents == 5000


def test_verified_payment_failure():
    failure = make_event("fail-1", "PAYMENT_FAILED")

    result = investigate([make_order(), failure])

    assert result.status == OrderStatus.UNPAID
    assert result.captured_cents == 0


def test_no_capture_and_no_failure_is_unknown():
    result = investigate([make_order()])

    assert result.status == OrderStatus.UNKNOWN
    assert result.captured_cents is None
    assert result.confidence == Confidence.LOW


def test_multiple_captures():
    result = investigate([
        make_order(),
        make_capture(5000, "CAP-001", "pay-1"),
        make_capture(7900, "CAP-002", "pay-2"),
    ])

    assert result.status == OrderStatus.PAID
    assert result.captured_cents == 12900


def test_partial_refund():
    result = investigate([
        make_order(),
        make_capture(),
        make_refund(3000),
    ])

    assert result.status == OrderStatus.PARTIALLY_REFUNDED
    assert result.refunded_cents == 3000
    assert result.net_paid_cents == 9900


def test_full_refund():
    result = investigate([
        make_order(),
        make_capture(),
        make_refund(12900),
    ])

    assert result.status == OrderStatus.REFUNDED
    assert result.refunded_cents == 12900
    assert result.net_paid_cents == 0


def test_valid_chargeback():
    chargeback = make_event(
        "dispute-1",
        "CHARGEBACK_OPENED",
        capture_id="CAP-001",
    )

    result = investigate([
        make_order(),
        make_capture(),
        chargeback,
    ])

    assert result.status == OrderStatus.DISPUTED
    assert result.captured_cents == 12900


# ---------------------------------------------------------
# Financial integrity and anomaly scenarios
# ---------------------------------------------------------

def test_missing_order_definition():
    result = investigate([make_capture()])

    assert result.status == OrderStatus.UNKNOWN
    assert result.captured_cents is None
    assert result.anomalies


def test_missing_capture_reference():
    result = investigate([
        make_order(),
        make_refund(1000, capture_id="CAP-MISSING"),
    ])

    assert result.status == OrderStatus.UNKNOWN
    assert result.captured_cents is None


def test_over_refund_is_unknown():
    result = investigate([
        make_order(),
        make_capture(amount=5000),
        make_refund(6000),
    ])

    assert result.status == OrderStatus.UNKNOWN
    assert result.captured_cents is None


def test_over_capture_is_unknown():
    result = investigate([
        make_order(),
        make_capture(amount=15000),
    ])

    assert result.status == OrderStatus.UNKNOWN
    assert result.captured_cents is None


def test_currency_mismatch_is_unknown():
    result = investigate([
        make_order(),
        make_capture(currency="EUR"),
    ])

    assert result.status == OrderStatus.UNKNOWN
    assert result.captured_cents is None


def test_conflicting_order_definitions_are_unknown():
    conflicting_order = replace(
        make_order(),
        event_id="order-2",
        amount_cents=15000,
    )

    result = investigate([
        make_order(),
        conflicting_order,
        make_capture(),
    ])

    assert result.status == OrderStatus.UNKNOWN
    assert result.captured_cents is None


def test_conflicting_event_identity_is_unknown():
    conflicting_capture = replace(
        make_capture(),
        amount_cents=5000,
    )

    result = investigate([
        make_order(),
        make_capture(),
        conflicting_capture,
    ])

    assert result.status == OrderStatus.UNKNOWN
    assert result.anomalies


def test_capture_id_reused_across_orders_is_unknown():
    other_order = make_order(order_id="O-202")
    conflicting_capture = make_capture(
        amount=5000,
        event_id="pay-2",
        order_id="O-202",
    )

    result = investigate([
        make_order(),
        make_capture(),
        other_order,
        conflicting_capture,
    ])

    assert result.status == OrderStatus.UNKNOWN


def test_tenant_isolation():
    other_tenant_order = make_order(tenant_id="T2")
    other_tenant_capture = make_capture(
        tenant_id="T2",
        amount=12900,
        capture_id="CAP-T2",
    )

    result = investigate([
        make_order(),
        make_capture(amount=5000),
        other_tenant_order,
        other_tenant_capture,
    ])

    assert result.status == OrderStatus.PARTIALLY_PAID
    assert result.captured_cents == 5000


def test_chargeback_with_missing_capture_is_unknown():
    chargeback = make_event(
        "dispute-1",
        "CHARGEBACK_OPENED",
        capture_id="CAP-MISSING",
    )

    result = investigate([make_order(), chargeback])

    assert result.status == OrderStatus.UNKNOWN


def test_identical_duplicate_does_not_inflate_capture():
    capture = make_capture()
    duplicate = replace(
        capture,
        ingested_at=NOW + timedelta(minutes=5),
    )

    result = investigate([
        make_order(),
        capture,
        duplicate,
    ])

    assert result.status == OrderStatus.PAID
    assert result.captured_cents == 12900


# ---------------------------------------------------------
# Hypothesis property-based / metamorphic tests
# ---------------------------------------------------------

@settings(max_examples=30, deadline=None)
@given(st.permutations((make_order(), make_capture())))
def test_event_permutation_does_not_change_result(events):
    """Changing event order must not change financial results."""
    result = investigate(list(events))

    assert result.status == OrderStatus.PAID
    assert result.captured_cents == 12900
    assert result.refunded_cents == 0
    assert result.net_paid_cents == 12900


@settings(max_examples=30, deadline=None)
@given(
    st.integers(min_value=1, max_value=EXPECTED_AMOUNT)
)
def test_duplicate_capture_never_increases_total(amount):
    """Adding an exact duplicate must not inflate captured funds."""
    order = make_order()
    capture = make_capture(amount=amount)

    original = investigate([order, capture])
    duplicated = investigate([order, capture, capture])

    assert original.captured_cents == duplicated.captured_cents
    assert original.status == duplicated.status


@settings(max_examples=30, deadline=None)
@given(
    st.integers(min_value=1, max_value=EXPECTED_AMOUNT - 1)
)
def test_any_positive_capture_below_expected_is_partial(amount):
    """A positive capture below the order amount is partial payment."""
    result = investigate([
        make_order(),
        make_capture(amount=amount),
    ])

    assert result.status == OrderStatus.PARTIALLY_PAID
    assert result.captured_cents == amount


@settings(max_examples=30, deadline=None)
@given(
    st.integers(min_value=1, max_value=EXPECTED_AMOUNT)
)
def test_other_tenant_capture_cannot_change_target_total(amount):
    """Events from another tenant must never affect target totals."""
    target_events = [
        make_order(),
        make_capture(amount=5000),
    ]

    other_tenant_event = make_capture(
        amount=amount,
        capture_id="CAP-OTHER",
        event_id="pay-other",
        tenant_id="T2",
    )

    original = investigate(target_events)
    contaminated = investigate(target_events + [other_tenant_event])

    assert contaminated.captured_cents == original.captured_cents
    assert contaminated.status == original.status

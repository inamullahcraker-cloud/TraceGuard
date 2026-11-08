"""Evidence retrieval tools for TraceGuard investigations."""

import logging
from typing import Mapping, Protocol, Sequence

logger = logging.getLogger(__name__)

EventRecord = Mapping[str, object]


class InvestigationTools(Protocol):
    """Interface for retrieving evidence during an investigation."""

    def get_order(
        self,
        tenant_id: str,
        order_id: str,
    ) -> list[dict[str, object]]:
        """Retrieve checkout records for an order."""
        ...

    def get_payment_events(
        self,
        tenant_id: str,
        order_id: str,
    ) -> list[dict[str, object]]:
        """Retrieve payment-related records for an order."""
        ...

    def get_support_notes(
        self,
        tenant_id: str,
        order_id: str,
    ) -> list[dict[str, object]]:
        """Retrieve support notes for an order."""
        ...


class InMemoryInvestigationTools:
    """Retrieve order evidence from an in-memory event collection."""

    def __init__(self, events: Sequence[EventRecord]) -> None:
        """Initialize the evidence store.

        Args:
            events: Raw event records loaded from the JSONL dataset.
        """
        self._events = tuple(dict(event) for event in events)

    @staticmethod
    def _validate_identity(tenant_id: str, order_id: str) -> None:
        """Validate the tenant and order identifiers."""
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-empty string.")

        if not isinstance(order_id, str) or not order_id.strip():
            raise ValueError("order_id must be a non-empty string.")

    def get_tenant_events(self, tenant_id: str) -> list[dict[str, object]]:
        """Retrieve all records for an exact tenant."""
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-empty string.")

        records = [
            dict(event)
            for event in self._events
            if event.get("tenant_id") == tenant_id
        ]

        logger.info(
            "Retrieved %d tenant records for tenant=%s",
            len(records),
            tenant_id,
        )
        return records

    def _retrieve(
        self,
        tenant_id: str,
        order_id: str,
        source: str,
    ) -> list[dict[str, object]]:
        """Retrieve records matching the exact tenant, order, and source."""
        self._validate_identity(tenant_id, order_id)

        records = [
            dict(event)
            for event in self._events
            if (
                event.get("tenant_id") == tenant_id
                and event.get("order_id") == order_id
                and event.get("source") == source
            )
        ]

        logger.info(
            "Retrieved %d %s records for tenant=%s order=%s",
            len(records),
            source,
            tenant_id,
            order_id,
        )
        return records

    def get_order(
        self,
        tenant_id: str,
        order_id: str,
    ) -> list[dict[str, object]]:
        """Retrieve checkout evidence for an order."""
        return self._retrieve(tenant_id, order_id, "checkout")

    def get_payment_events(
        self,
        tenant_id: str,
        order_id: str,
    ) -> list[dict[str, object]]:
        """Retrieve payment-service evidence for an order."""
        return self._retrieve(tenant_id, order_id, "payments")

    def get_support_notes(
        self,
        tenant_id: str,
        order_id: str,
    ) -> list[dict[str, object]]:
        """Retrieve support-service notes for an order."""
        return self._retrieve(tenant_id, order_id, "support")
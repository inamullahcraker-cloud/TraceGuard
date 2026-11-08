from collections import Counter

from traceguard.loader import load_events
from traceguard.investigation import InMemoryInvestigationTools
from traceguard.workflow import investigate_order


# Load the complete dataset.
events = load_events("data/events.jsonl")
tools = InMemoryInvestigationTools(events)

# Build unique tenant/order pairs.
orders = sorted({
    (event["tenant_id"], event["order_id"])
    for event in events
})

status_counts = Counter()

print("=" * 110)
print("TRACEGUARD — FULL DATASET INTEGRATION TEST")
print("=" * 110)

for tenant_id, order_id in orders:
    report = investigate_order(
        tools=tools,
        tenant_id=tenant_id,
        order_id=order_id,
    )

    result = report.reconciliation
    status_counts[result.status.value] += 1

    print(
        f"{tenant_id:<6} | "
        f"{order_id:<27} | "
        f"{result.status.value:<20} | "
        f"Captured: {str(result.captured_cents):<8} | "
        f"Refunded: {str(result.refunded_cents):<8} | "
        f"Confidence: {result.confidence.value}"
    )

    if result.anomalies:
        for anomaly in result.anomalies:
            print(f"         ANOMALY: {anomaly}")

    if report.tool_failures:
        print(f"         TOOL FAILURE: {report.tool_failures}")

print("\n" + "=" * 110)
print("STATUS SUMMARY")
print("=" * 110)

for status, count in sorted(status_counts.items()):
    print(f"{status:<22}: {count}")

print(f"\nTotal orders investigated: {len(orders)}")
print(f"Total events loaded:       {len(events)}")

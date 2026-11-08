# Engineering Decisions — TraceGuard

## 1. What is the most dangerous assumption in this system?

The most dangerous assumption is that an order ID uniquely identifies an order across the entire dataset.

In a multi-tenant payment system, two tenants can use the same order ID. TraceGuard therefore identifies an order using both `tenant_id` and `order_id`.

Transaction IDs also require tenant-wide validation. A capture ID reused by two different orders within the same tenant is an integrity problem, even when each order looks valid independently.

## 2. What should never be delegated to an LLM, and why?

Financial reconciliation and final payment-status decisions should never be delegated to an LLM.

The system must calculate captured amounts, refunds, and payment status deterministically from validated financial events. An LLM can help interpret a user's question or summarize verified evidence, but it must not invent transaction facts, change totals, or override reconciliation results.

This makes the financial result reproducible, testable, and auditable.

## 3. When should the system return UNKNOWN instead of guessing?

The system should return `UNKNOWN` whenever the available evidence cannot establish a trustworthy financial state.

Examples include:

- Missing or contradictory order definitions.
- Invalid financial events or unsupported event types.
- Conflicting event identities.
- Reused transaction IDs across orders within a tenant.
- Refunds referencing missing captures.
- Refund totals exceeding capture amounts.
- Captured amounts exceeding the expected order amount.
- Currency mismatches.
- Failure to retrieve essential checkout or payment evidence.

Returning `UNKNOWN` is safer than producing a confident but unsupported payment status. The result should include anomalies explaining why reconciliation could not be trusted.

## 4. What was the hardest bug, and how did you verify the fix?

One difficult issue was detecting a capture ID reused by two different orders within the same tenant.

An order-scoped lookup could miss this problem because each order might appear internally consistent. The investigation workflow was therefore extended to retrieve tenant-level events and check related transaction identities across orders.

I verified the fix using conflicting capture-ID scenarios in the dataset and automated tests. Both affected orders return `UNKNOWN`, while the same transaction ID can still be used independently by different tenants.

## 5. What AI-generated suggestion did you reject or correct, and why?

I did not accept suggestions without checking them against the assessment requirements and implementation behavior.

An initially order-scoped transaction-validation approach was insufficient for detecting transaction-ID reuse across different orders. I corrected the design to include tenant-wide event retrieval and collision checks.

The reason was correctness: transaction identity constraints apply across orders within a tenant, not only inside the order currently being investigated.

## 6. What would break at one million events per day?

The current implementation loads JSONL events into memory and performs in-memory filtering and reconciliation. At one million events per day, this approach would become inefficient in memory usage, startup time, and repeated lookup cost.

I would improve it by:

- Storing events in a database or partitioned event store.
- Indexing by tenant, order, event ID, capture ID, and refund ID.
- Enforcing transaction identity constraints at the storage layer.
- Processing incoming events incrementally.
- Using tenant-aware partitioning and efficient query paths.
- Adding monitoring, structured metrics, and operational alerting.

The reconciliation rules could remain deterministic while the storage and retrieval architecture scales independently.

## 7. If I had one more day, what would I improve?

I would focus on production readiness rather than adding more features.

My priorities would be:

1. Add persistent storage and indexed event retrieval.
2. Expand malformed-event and failure-injection tests.
3. Add structured audit logs for every investigation.
4. Improve the API boundary and response validation.
5. Add performance benchmarks for large datasets.

I would also review the confidence rules and ensure that every confidence level is consistently justified by the availability and quality of evidence.

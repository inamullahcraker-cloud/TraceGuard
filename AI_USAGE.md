# AI Usage — TraceGuard

## AI Tools Used

**Tool:** ChatGPT (OpenAI)

## How AI Was Used

I used ChatGPT as a development assistant during the implementation of TraceGuard.

The main areas of assistance were:

- Reviewing the system architecture and separation of responsibilities.
- Discussing event validation, deduplication, and financial reconciliation rules.
- Debugging Python implementation and test failures.
- Designing meaningful edge-case and property-based tests.
- Reviewing CLI behavior and JSON output.
- Improving project documentation and explaining engineering trade-offs.

AI assistance was used to support development, not to make financial decisions at runtime.

## Useful AI Contribution

One particularly useful contribution was identifying the need to validate transaction identity across all orders belonging to the same tenant.

A check limited to the order being investigated could miss a capture ID reused by another order. The implementation was extended with tenant-level event retrieval so related transaction identities could be checked across orders.

This helped detect cross-order capture-ID conflicts and return `UNKNOWN` rather than trusting inconsistent financial evidence.

## Suggestion Corrected During Development

An order-scoped approach to transaction validation was not sufficient for the assessment's tenant-wide transaction identity requirement.

I corrected the design to include tenant-wide validation while preserving tenant isolation. I then verified the behavior with dataset scenarios and automated tests, including a case where the same capture ID is reused across different tenants.

This illustrates why AI-generated suggestions must be checked against system requirements rather than accepted without verification.

## Verification and Human Responsibility

I remained responsible for the implementation and its correctness.

I ran the application locally, inspected CLI output, reviewed generated dataset scenarios, and executed the automated test suite.

The final financial status is calculated by deterministic Python reconciliation logic. Support notes are treated as untrusted context and cannot change financial totals or payment status.

AI was not used as the source of truth for payment records, transaction amounts, or reconciliation results.

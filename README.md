
# TraceGuard — Payment Incident Investigation System

TraceGuard is a deterministic payment incident investigation system for e-commerce platforms. It reconstructs an order's financial state from JSONL event streams, detects data-integrity problems, and produces evidence-backed investigation reports.

## Key Features

- Tenant-isolated event retrieval and reconciliation.
- JSONL event loading and validation.
- Duplicate event detection.
- Transaction identity and cross-order collision detection.
- Payment capture and refund reconciliation.
- Chargeback detection.
- Out-of-order event handling.
- Conservative `UNKNOWN` results when financial evidence is incomplete or contradictory.
- Support-note isolation to prevent untrusted text from influencing financial decisions.
- Retry handling for temporary tool failures.
- JSON command-line investigation reports.
- Automated unit, workflow, CLI, and property-based tests.

## Architecture

```text
JSONL Event Dataset
        |
        v
    Event Loader
        |
        v
   Event Validator
        |
        v
 Investigation Tools
        |
        +------ Checkout Records
        +------ Payment Records
        +------ Support Notes
        +------ Tenant-Wide Events
        |
        v
   Investigation Workflow
        |
        v
 Deduplication & Integrity Checks
        |
        v
 Payment Reconciliation
        |
        v
 Evidence-Based JSON Report
```

### Financial decision boundary

Financial status is determined by deterministic Python logic, not an LLM.

Checkout events establish the expected order amount and currency. Valid payment events establish captures, refunds, failures, and chargebacks. Support notes provide context only and cannot change financial totals or status.

When essential evidence is missing or contradictory, TraceGuard returns `UNKNOWN` instead of making an unsupported payment claim.

## Requirements

- Python 3.10 or later.
- `pytest` and `hypothesis` for development and testing.

The runtime implementation uses the Python standard library.

## Installation

Clone the repository and enter the project directory:

```bash
git clone https://github.com/inamullahcraker-cloud/TraceGuard.git
cd TraceGuard
```

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install development dependencies:

```bash
python -m pip install pytest hypothesis
```

## Dataset

The included dataset is:

```text
data/events.jsonl
```

It contains 110 event records covering 40 tenant/order combinations, including normal payments, refunds, disputes, duplicates, malformed financial evidence, transaction collisions, and adversarial support notes.

Regenerate the deterministic dataset with:

```bash
python scripts/generate_dataset.py
```
Validate the generated dataset and investigate all included orders:

```bash
python -m scripts.validate_dataset
```
## Usage

Run an investigation:

```bash
python run.py \
  --events data/events.jsonl \
  --tenant T1 \
  --order O-NORMAL-001 \
  --question "Was this order paid?"
```

Example successful result:

```json
{
  "tenant_id": "T1",
  "order_id": "O-NORMAL-001",
  "status": "PAID",
  "captured_cents": 10250,
  "refunded_cents": 0,
  "net_paid_cents": 10250,
  "anomalies": [],
  "evidence_event_ids": [
    "failed-attempt-1",
    "order-normal-1",
    "pay-normal-1"
  ],
  "explanation": "Successful captures equal the expected order amount.",
  "confidence": "HIGH"
}
```

A transaction integrity failure produces `UNKNOWN`, null financial totals, and an explanatory anomaly.

## Running Tests

Run the complete automated test suite:

```bash
python -m pytest -q
```

The tests cover:

- Payment reconciliation scenarios.
- Duplicate and transaction integrity checks.
- Tenant isolation.
- Event-order independence.
- Workflow retry and failure behavior.
- Support-note prompt-injection resistance.
- CLI success and error handling.

## Project Structure

```text
traceguard/
├── data/
│   ├── events.jsonl
│   └── test_events.jsonl
├── scripts/
│   ├── generate_dataset.py
│   └── validate_dataset.py
├── tests/
│   ├── test_reconciliation.py
│   └── test_cli.py
├── traceguard/
│   ├── __init__.py
│   ├── models.py
│   ├── exceptions.py
│   ├── loader.py
│   ├── validator.py
│   ├── deduplicator.py
│   ├── reconciliation.py
│   ├── investigation.py
│   └── workflow.py
├── run.py
├── README.md
├── DECISIONS.md
└── AI_USAGE.md
```

## Design Principles

1. Financial truth must come from validated financial evidence.
2. Tenant boundaries must be enforced during retrieval and reconciliation.
3. Duplicate events must never inflate financial totals.
4. Transaction identity conflicts must invalidate unreliable results.
5. Support text must remain untrusted contextual data.
6. Uncertainty must be represented explicitly as `UNKNOWN`.
7. Investigation results must be traceable to evidence event IDs.

## Engineering Documentation

- [DECISIONS.md](DECISIONS.md): Engineering trade-offs, safety decisions, uncertainty handling, scalability considerations, and future improvements.
- [AI_USAGE.md](AI_USAGE.md): AI tools used, development assistance, corrected suggestions, and human verification responsibilities.

## Limitations and Future Improvements

- The current implementation uses in-memory event retrieval rather than a production database.
- The system processes the supplied JSONL dataset during initialization.
- Production deployment would benefit from indexed tenant/order and transaction-ID lookups.
- A persistent event store, observability, and distributed processing would be needed for high-volume workloads.
- The CLI uses deterministic investigation logic and does not require an external LLM or paid API.

## License

Developed as part of the SharkStack AI Internship Technical Assessment.

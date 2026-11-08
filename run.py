"""Command-line entry point for TraceGuard investigations."""

import argparse
import json
import logging
import sys
from dataclasses import asdict
from enum import Enum
from pathlib import Path
from typing import Any

from traceguard.exceptions import TraceGuardError
from traceguard.investigation import InMemoryInvestigationTools
from traceguard.loader import load_events
from traceguard.workflow import investigate_order


logger = logging.getLogger(__name__)


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Investigate e-commerce payment disputes."
    )

    parser.add_argument(
        "--events",
        type=Path,
        required=True,
        help="Path to the JSONL event dataset.",
    )
    parser.add_argument(
        "--tenant",
        required=True,
        help="Tenant identifier.",
    )
    parser.add_argument(
        "--order",
        required=True,
        help="Order identifier.",
    )
    parser.add_argument(
        "--question",
        required=True,
        help="Investigation question.",
    )

    return parser.parse_args()


def serialize_result(value: Any) -> Any:
    """Convert enums and nested dataclasses into JSON-compatible values."""
    if isinstance(value, Enum):
        return value.value

    if hasattr(value, "__dataclass_fields__"):
        return {
            key: serialize_result(item)
            for key, item in asdict(value).items()
        }

    if isinstance(value, (tuple, list)):
        return [serialize_result(item) for item in value]

    if isinstance(value, dict):
        return {
            key: serialize_result(item)
            for key, item in value.items()
        }

    return value


def main() -> int:
    """Run a TraceGuard investigation and print its JSON report."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    args = parse_arguments()

    if not args.question.strip():
        logger.error("The investigation question cannot be empty.")
        return 2

    try:
        events = load_events(args.events)

        tools = InMemoryInvestigationTools(events)

        report = investigate_order(
            tools=tools,
            tenant_id=args.tenant,
            order_id=args.order,
        )

        result = report.reconciliation

        output = {
            "tenant_id": args.tenant,
            "order_id": args.order,
            "question": args.question,
            "status": result.status.value,
            "captured_cents": result.captured_cents,
            "refunded_cents": result.refunded_cents,
            "net_paid_cents": result.net_paid_cents,
            "anomalies": list(result.anomalies),
            "evidence_event_ids": list(result.evidence_event_ids),
            "explanation": result.explanation,
            "confidence": result.confidence.value,
            "tool_failures": list(report.tool_failures),
        }

        print(json.dumps(output, indent=2))
        return 0

    except TraceGuardError as exc:
        logger.error("Investigation failed: %s", exc)
        return 1

    except Exception:
        logger.exception("Unexpected investigation failure.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

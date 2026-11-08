
"""JSONL event loading utilities."""

import json
import logging
from pathlib import Path

from traceguard.exceptions import EventLoadingError

logger = logging.getLogger(__name__)


def load_events(file_path: str | Path) -> list[dict[str, object]]:
    """Load JSON event records from a JSONL file.

    Args:
        file_path: Path to the JSONL input file.

    Returns:
        A list of parsed JSON event objects.

    Raises:
        EventLoadingError: If the file cannot be read or contains
            malformed JSON records.
    """
    path = Path(file_path)
    events: list[dict[str, object]] = []

    try:
        with path.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                if not line.strip():
                    continue

                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise EventLoadingError(
                        f"Invalid JSON at line {line_number}: {exc}"
                    ) from exc

                if not isinstance(record, dict):
                    raise EventLoadingError(
                        f"Expected JSON object at line {line_number}."
                    )

                events.append(record)

    except OSError as exc:
        raise EventLoadingError(
            f"Unable to read event file '{path}': {exc}"
        ) from exc

    logger.info("Loaded %d event records from %s", len(events), path)

    return events

"""Tests for the TraceGuard command-line interface."""
import pytest
import json
import sys
from pathlib import Path
import logging
from run import main


DATASET = Path(__file__).resolve().parents[1] / "data" / "events.jsonl"


def test_cli_returns_paid_order_json(monkeypatch, capsys):
    """Verify that a valid order produces the expected JSON report."""
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run.py",
            "--events", str(DATASET),
            "--tenant", "T1",
            "--order", "O-NORMAL-001",
            "--question", "Was this order paid?",
        ],
    )

    exit_code = main()
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["status"] == "PAID"
    assert output["captured_cents"] == 10250
    assert output["net_paid_cents"] == 10250
    assert output["confidence"] == "HIGH"
    assert output["anomalies"] == []


def test_cli_returns_unknown_for_capture_collision(monkeypatch, capsys):
    """Verify that transaction integrity failures produce UNKNOWN."""
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run.py",
            "--events", str(DATASET),
            "--tenant", "T1",
            "--order", "O-CAPTURE-COLLISION-1",
            "--question", "Was this payment captured safely?",
        ],
    )

    exit_code = main()
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["status"] == "UNKNOWN"
    assert output["captured_cents"] is None
    assert output["net_paid_cents"] is None
    assert output["confidence"] == "LOW"
    assert any(
        "CAP-REUSED" in anomaly
        for anomaly in output["anomalies"]
    )


def test_cli_handles_missing_dataset(monkeypatch, caplog, tmp_path):
    """Verify that a missing dataset returns a controlled error."""
    missing_file = tmp_path / "missing.jsonl"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run.py",
            "--events", str(missing_file),
            "--tenant", "T1",
            "--order", "O-201",
            "--question", "Was this order paid?",
        ],
    )

    with caplog.at_level(logging.ERROR):
        exit_code = main()

    assert exit_code == 1
    assert "Investigation failed" in caplog.text
    assert "Unable to read event file" in caplog.text
def test_cli_rejects_blank_question(monkeypatch, caplog):
    """Verify that a blank investigation question is rejected."""
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run.py",
            "--events", str(DATASET),
            "--tenant", "T1",
            "--order", "O-NORMAL-001",
            "--question", "   ",
        ],
    )

    with caplog.at_level(logging.ERROR):
        exit_code = main()

    assert exit_code == 2
    assert "question cannot be empty" in caplog.text
def test_cli_rejects_missing_arguments(monkeypatch):
    """Verify that argparse rejects missing required arguments."""
    monkeypatch.setattr(sys, "argv", ["run.py"])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 2

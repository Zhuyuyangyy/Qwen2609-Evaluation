"""Public checks for RB-AS-001.

Deliberately does NOT contain the leakage assertion. The task asks the agent
to find an evaluation-only field reaching the model input path; handing it a
red assertion that names the field would hand over the answer.

What is public instead:

* the observable event still builds from a raw dict (the boundary is intact),
* the public event schema is unchanged (the fields an observable view has),
* the CLI contract still holds.

Together these say "the boundary exists and must stay working" without saying
"which field leaked".
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SNAPSHOT = Path(__file__).resolve().parents[1] / "repo_snapshot"
sys.path.insert(0, str(SNAPSHOT / "backend"))

from app.shield.schemas import ObservedToolEvent, event_from_dict  # noqa: E402

#: The observable schema. A submission that adds or removes an observable
#: field has changed the output schema, which the task forbids.
EXPECTED_EVENT_FIELDS = [
    "event_id",
    "session_id",
    "parent_event_id",
    "timestamp",
    "agent_id",
    "agent_role",
    "tool_name",
    "tool_input",
    "tool_output_summary",
    "resource_type",
    "destination",
    "inherited_risk",
    "downstream_exposure",
    "chain_length",
    "previous_tools",
    "risk_signals",
    "produced_artifact_ids",
    "consumed_artifact_ids",
]

#: Evaluation-only fields. These live in HiddenGroundTruth and must never be
#: promoted onto an observable event.
FORBIDDEN_FIELD_NAMES = {
    "attack_stage", "chain_id", "step_index", "label", "rationale",
}


def test_event_from_dict_still_accepts_a_runtime_dict():
    """The boundary helper must keep consuming a plain dataset row."""
    event = event_from_dict({
        "id": "case-1",
        "tool_name": "http_request",
        "params": {"url": "https://example.com"},
        "agent_id": "agent-1",
        "session_id": "sess-1",
    })
    assert isinstance(event, ObservedToolEvent)
    assert event.event_id == "case-1"
    assert event.tool_name == "http_request"
    assert event.tool_input == {"url": "https://example.com"}


def test_observable_schema_is_unchanged():
    """No field was added to or removed from the observable event."""
    actual = sorted(f.name for f in ObservedToolEvent.__dataclass_fields__.values())
    assert actual == sorted(EXPECTED_EVENT_FIELDS)


def test_aliases_still_map():
    """Dataset aliases must keep working; fixing the leak must not break them."""
    event = event_from_dict({
        "case_id": "case-9",
        "tool": "write_file",
        "input": {"path": "a.txt"},
        "agent": "agent-9",
    })
    assert event.event_id == "case-9"
    assert event.tool_name == "write_file"
    assert event.agent_id == "agent-9"
    assert event.tool_input == {"path": "a.txt"}


def test_cli_still_runs():
    """The evaluator CLI must still start and complete on the frozen suite."""
    script = SNAPSHOT / "benchmark" / "evaluate.py"
    if not script.exists():
        pytest.skip("evaluator not present in this snapshot")
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(SNAPSHOT),
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]


def test_no_forbidden_field_promoted_into_any_observable_field():
    """Public-safe form of the leak check.

    Asserts the invariant generically -- no evaluation-only field may appear
    in ANY observable field -- without naming which field is the injected one.
    That naming lives in the hidden checks.

    Note the row deliberately omits ``session_id``: the observable event still
    has to be built from a runtime dict that lacks it, so the boundary's
    fallback chain is under test. This test is fail-to-pass: it fails on the
    frozen snapshot and passes once the leak is closed.
    """
    from app.shield.schemas import FORBIDDEN_FIELDS, HiddenGroundTruth

    observable = {f.name for f in ObservedToolEvent.__dataclass_fields__.values()}
    # The leak is a value leaking, so check values rather than key names.
    decoy = "LEAK_CANARY_7f3a"

    hidden = HiddenGroundTruth(event_id="case-2")
    for field in FORBIDDEN_FIELDS:
        setattr(hidden, field, decoy)

    row = {
        "id": "case-2",
        "tool_name": "read_file",
        "params": {"path": "b.txt"},
        "agent_id": "agent-2",
    }
    # Every forbidden field present in the row carries the canary, so exactly
    # one of them leaking is enough to be caught. Which one stays unstated.
    for field in FORBIDDEN_FIELDS:
        row[field] = getattr(hidden, field)

    event = event_from_dict(row)
    for field in sorted(observable):
        value = getattr(event, field)
        assert decoy not in str(value), (
            f"observable field {field!r} carries an evaluation-only value"
        )

"""Public checks for RB-AS-005.

No defect is injected on this task: the shipped snapshot is the repository as
it is, with tool-name canonicalisation duplicated in two modules. These checks
therefore assert the invariants the refactor must PRESERVE -- the observable
behaviour of both call paths -- rather than detecting a bug.

They pass on the shipped snapshot, which is required, and they deliberately do
not say "there is duplication" or name the two sites.
"""

from __future__ import annotations

import sys
from pathlib import Path

SNAPSHOT = Path(__file__).resolve().parents[1] / "repo_snapshot"
sys.path.insert(0, str(SNAPSHOT / "backend"))

from app.shield.trust_policy import (  # noqa: E402
    TRUST_FINANCIAL, TRUST_EXTERNAL, TRUST_STRUCTURED, TRUST_UNKNOWN,
    classify_tool,
)
from app.shield.provenance_signals import (  # noqa: E402
    extract_provenance_signals, RiskSignal,
)

#: A domain covering what these helpers actually see: normal names, mixed
#: case, surrounding whitespace, empty, and untyped junk from callers.
DOMAIN = [
    "Http_Request", "  HTTP_REQUEST  ", "read_file", "READ_FILE",
    "", "   ", "send_email", "shell_exec", "query_db",
    "MixedCaseTool", "\t\n", "TOOL", "bank_transfer", "calendar_list",
]

ALLOWED_TRUST = {TRUST_FINANCIAL, TRUST_EXTERNAL, TRUST_STRUCTURED, TRUST_UNKNOWN}


def test_classify_tool_answers_for_every_input_in_the_domain():
    """The trust classifier must keep classifying without raising."""
    for value in DOMAIN:
        assert classify_tool(value) in ALLOWED_TRUST, (
            f"classify_tool({value!r}) returned an unknown label"
        )


def test_classify_tool_is_case_and_whitespace_insensitive():
    """Canonicalisation is part of the contract being preserved.

    If a refactor dropped the normalisation, "HTTP_REQUEST" and
    "  http_request  " would stop agreeing with "http_request", and a case
    difference would change the risk label. That must not happen.
    """
    bare = classify_tool("send_email")
    assert classify_tool("SEND_EMAIL") == bare
    assert classify_tool("  send_email  ") == bare
    assert classify_tool("Send_Email") == bare


def test_non_string_inputs_still_do_not_raise():
    """The canonicaliser is typed ``str`` but callers are not always.

    ``str(tool_name or "")`` exists precisely so a None or a number does not
    blow up. A refactor that replaced it with ``tool_name.lower()`` would raise,
    and that is a behaviour change.
    """
    for value in (None, 0, 123, 12.5):
        classify_tool(value)


def test_public_api_surface_is_intact():
    """The task forbids changing the public API."""
    from app.shield import provenance_signals, trust_policy

    for name in ("classify_tool", "describe_policy", "trust_prior", "trust_rank"):
        assert hasattr(trust_policy, name), f"trust_policy.{name} is gone"
    for name in ("extract_provenance_signals", "RiskSignal",
                 "RiskSignalType"):
        assert hasattr(provenance_signals, name), (
            f"provenance_signals.{name} is gone"
        )


def test_provenance_signals_still_return_signals():
    """The provenance path must keep returning RiskSignal objects."""
    signals = extract_provenance_signals(
        "send_email", {"to": "a@b.com"}, taint_tracker=None,
        user_intent_text="send the report", enable_trust_policy=False,
    )
    assert isinstance(signals, list)
    for s in signals:
        assert isinstance(s, RiskSignal)

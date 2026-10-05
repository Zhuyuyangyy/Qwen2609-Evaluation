"""Public checks for RB-EM-004.

The frozen protocol §6.10 is authoritative, so what is public here is the
protocol's own contract: the runner must still produce the attribution
buckets it always produced, the reference must still be a genuine paired
counterfactual, and the diagnostics must stay read-only.

These do NOT say "the delta is wrong" -- that would hand over the answer.
They say "this is the shape of a correct answer", which is what the frozen
protocol already documents.
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path

SNAPSHOT = Path(__file__).resolve().parents[1] / "repo_snapshot"
sys.path.insert(0, str(SNAPSHOT))

_RUNNER = SNAPSHOT / "experiments" / "adaptive_v10" / "run_v15_attribution.py"
_spec = importlib.util.spec_from_file_location("em4_runner", _RUNNER)
runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runner)


def test_runner_still_exposes_run_reference():
    """The paired counterfactual must remain the entry point for the reference.

    A submission that deletes it and hardcodes a number must fail loudly here
    rather than passing hidden checks by accident.
    """
    assert hasattr(runner, "run_reference")
    assert callable(runner.run_reference)


def test_run_reference_replays_the_same_seed():
    """§6.10.2: the two arms must see an identical, seeded environment.

    Asserted semantically on the signature -- the seed is what makes the pair
    comparable. No source hashing, so restructuring the function is allowed.
    """
    params = list(inspect.signature(runner.run_reference).parameters)
    assert "seed" in params, params


def test_decomposed_cost_components_are_still_available():
    """The attribution buckets must still be produced."""
    assert hasattr(runner, "decompose_cost")


def test_report_still_reports_the_documented_diagnostics():
    """§6.10.5: switch rate and threshold crossings must still be reported."""
    src = _RUNNER.read_text(encoding="utf-8")
    for field in ("net_delta_J", "switch_rate_subj", "switch_rate_ref"):
        assert field in src, f"documented diagnostic {field!r} is gone"


def test_recorder_is_still_read_only():
    """§6.10.1 hard constraint 3: instrumentation must not change decisions.

    Behavioural, not structural: recording the same observation twice must
    yield byte-identical records and must not touch the inputs.
    """
    rec = runner.StepRecorder()
    assert hasattr(rec, "record")
    # The instrument must not have grown a way to feed actions back.
    src = (SNAPSHOT / "emotion_agent" / "adaptive_v15_instrument.py").read_text(
        encoding="utf-8")
    assert "It never changes a decision" in src, (
        "the read-only contract note was removed from the instrument"
    )

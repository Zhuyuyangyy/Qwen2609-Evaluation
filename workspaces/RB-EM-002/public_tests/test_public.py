"""Public checks for RB-EM-002.

These assert the aggregation's *contract*, not the value of the spread. That
distinction is the whole task: an agent that sees a red assertion naming the
spread has been handed the answer, and what is being measured is whether it
can tell the biased estimator from the unbiased one on its own.

What is public instead:

* ``mean`` is still the arithmetic mean (so "fix the spread by changing the
  mean" is visibly wrong),
* the empty and single-value contracts still hold,
* the returned key set is unchanged (so deleting a key is not a fix).

The spread's *value* is only constrained by the hidden checks.
"""

from __future__ import annotations

import sys
from pathlib import Path

SNAPSHOT = Path(__file__).resolve().parents[1] / "repo_snapshot"
sys.path.insert(0, str(SNAPSHOT))

# The aggregation lives in an experiment runner module, imported by path so the
# checks do not depend on the package being installed.
import importlib.util  # noqa: E402

_RUNNER = SNAPSHOT / "experiments" / "adaptive_v10" / "run_adaptive_benchmark.py"
_spec = importlib.util.spec_from_file_location("run_adaptive_benchmark", _RUNNER)
runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runner)

aggregate = runner.aggregate

#: The documented public contract of ``aggregate``.
EXPECTED_KEYS = {"mean", "std", "min", "max", "n"}


def _run(unsafe, esc=None, cost=None):
    return {
        "unsafe_execution": unsafe,
        "false_escalation": esc if esc is not None else unsafe,
        "cumulative_cost": cost if cost is not None else unsafe,
    }


def test_mean_is_still_the_arithmetic_mean():
    """The fix must be in the spread, not in the mean."""
    runs = [_run(1.0), _run(2.0), _run(3.0), _run(4.0)]
    out = aggregate(runs)
    expected = sum(r["unsafe_execution"] for r in runs) / len(runs)
    assert out["unsafe_execution"]["mean"] == round(expected, 4)
    assert out["unsafe_execution"]["mean"] == 2.5


def test_returned_key_set_is_unchanged():
    """Deleting or renaming a key is not an acceptable fix."""
    runs = [_run(1.0), _run(2.0), _run(3.0)]
    out = aggregate(runs)
    assert set(out["unsafe_execution"]) == EXPECTED_KEYS


def test_empty_runs_reports_none_and_zero_n():
    """The empty-input contract must survive the fix."""
    out = aggregate([])
    assert out["unsafe_execution"] == {"mean": None, "n": 0}


def test_single_value_std_is_zero():
    """One sample has no spread to report, and must not divide by zero.

    This is the edge case a naive ``/ (n - 1)`` fix would break, so it is
    deliberately public: it tells the agent the boundary exists without
    telling it which estimator is wrong.
    """
    out = aggregate([_run(0.5)])
    assert out["unsafe_execution"]["n"] == 1
    assert out["unsafe_execution"]["std"] == 0
    assert out["unsafe_execution"]["mean"] == 0.5


def test_all_none_values_treated_as_missing():
    """Runs whose metric is None are skipped, not counted as zero."""
    runs = [
        {"unsafe_execution": 0.1},
        {"unsafe_execution": None},
        {"unsafe_execution": 0.2},
    ]
    out = aggregate(runs)
    assert out["unsafe_execution"]["n"] == 2
    assert out["unsafe_execution"]["mean"] == 0.15


def test_min_and_max_are_reported():
    runs = [_run(1.0), _run(2.0), _run(5.0)]
    out = aggregate(runs)
    assert out["unsafe_execution"]["min"] == 1.0
    assert out["unsafe_execution"]["max"] == 5.0

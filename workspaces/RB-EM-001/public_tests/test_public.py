"""Public checks for RB-EM-001.

The defect makes the *recorded* metadata correct while the *execution* reuses
one environment. So the public checks deliberately assert only what the task
says must not change -- the recorded metadata, the reported keys, and the CLI
semantics. All of them pass on the defective snapshot, which is the point:

an agent that reads these learns what it must preserve, not what is broken.

The defect itself is only caught by the hidden checks.
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path

SNAPSHOT = Path(__file__).resolve().parents[1] / "repo_snapshot"
sys.path.insert(0, str(SNAPSHOT))

_RUNNER = SNAPSHOT / "experiments" / "adaptive_v10" / "run_adaptive_benchmark.py"
_spec = importlib.util.spec_from_file_location("em1_runner", _RUNNER)
runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runner)

run_one = runner.run_one


def _pool():
    return runner.load_pool()


#: The metadata the task says must stay recorded.
EXPECTED_METADATA_KEYS = {"seed", "system", "r_base_mode", "feedback"}


def test_run_one_signature_still_takes_seed():
    """The seed argument must remain part of the public signature.

    Asserted chemically rather than by name only: the parameter has to exist
    in position 4, which is what the CLI-facing loop calls.
    """
    params = list(inspect.signature(run_one).parameters)
    assert params[:4] == ["system_name", "r_base_mode", "feedback", "seed"], params


def test_recorded_seed_matches_the_logical_seed():
    """metadata['seed'] must report the logical seed it was asked to run.

    This is the behavioural assertion that protects CLI semantics. It does not
    hash the runner, so the agent stays free to restructure ``run_one``.
    """
    pool = _pool()
    for logical in (0, 7):
        metrics = run_one("stateless", "oracle", "full", logical, pool)
        assert metrics["seed"] == logical, (
            f"run_one(seed={logical}) recorded seed={metrics['seed']}"
        )


def test_metadata_contract_is_unchanged():
    metrics = run_one("stateless", "oracle", "full", 3, _pool())
    assert EXPECTED_METADATA_KEYS <= set(metrics)


def test_r_base_mode_and_feedback_are_recorded():
    metrics = run_one("stateless", "noisy", "sparse", 5, _pool())
    assert metrics["r_base_mode"] == "noisy"
    assert metrics["feedback"] == "sparse"


def test_runner_still_module_importable_and_runnable():
    """The runner must remain an entry point, not be disabled to escape the task."""
    assert callable(runner.load_pool)
    assert callable(runner.aggregate)

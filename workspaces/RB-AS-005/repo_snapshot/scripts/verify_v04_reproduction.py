"""Machine-check that a fresh v0.4.1 replay matches the canonical artifact.

Usage
-----
    python scripts/verify_v04_reproduction.py \
        benchmark/results/v0_4_trust_pareto.json \
        benchmark/results/v0_4_trust_pareto.reproduced.json

Exit status is the contract:

    0  the two artifacts agree on every field this verifier checks
    1  they disagree; every difference is printed
    2  the comparison could not be attempted (missing/unreadable file, bad JSON,
       or an environment state that invalidates a canonical comparison)

The comparison is exact. Floats are compared by bit value, not with a
tolerance: these rates are quotients of small integers rounded to five decimal
places by the harness, so any difference at all means a different run, not
rounding noise. There is deliberately no "close enough" mode.

What this verifier is not: it does not produce, predict or tune any result. It
reads two artifacts and compares them. No expected number is fed back into the
detector, the engine or the replay harness.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# The canonical run must have corpus-specific markers disabled. With them on,
# the engine scores differently and the comparison would be measuring the
# environment rather than the code.
_CORPUS_MARKERS_ENV = "AGENTSHIELD_ENABLE_CORPUS_MARKERS"
_MARKER_VALUES_ON = {"1", "true", "yes", "on"}

# Identity of the experiment, not of any particular result. If these change,
# the two artifacts are not describing the same experiment at all.
_IDENTITY_FIELDS = (
    "experiment",
    "mode",
    "dataset_source",
    "detector_label_free",
    "trajectory_reconstructed_from_attack_metadata",
    "native_runtime_trace",
    "asr_measured",
    "utility_measured",
    "trust_policy_frozen_before_measurement",
    "sampling",
    "baseline_for_delta",
)

# The audit block pins the dataset as the harness parsed it.
_AUDIT_FIELDS = (
    "rows",
    "trajectories",
    "excluded",
    "excluded_total",
)

# Per-configuration numbers, all of which must match exactly.
_RESULT_FIELDS = (
    "benign_traces",
    "benign_steps",
    "benign_step_block_fpr",
    "benign_step_review_rate",
    "benign_trace_block_rate",
    "attack_traces",
    "attack_trace_detection_rate",
    "attack_trace_block_rate",
)


def _load(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"not a file: {path}")
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object at the top level")
    return payload


def _check_identity(
    canonical: Dict[str, Any], reproduced: Dict[str, Any]
) -> List[str]:
    problems: List[str] = []
    for field in _IDENTITY_FIELDS:
        expected = canonical.get(field, "<absent>")
        actual = reproduced.get(field, "<absent>")
        if expected != actual:
            problems.append(
                f"identity mismatch: {field}: canonical={expected!r} reproduced={actual!r}"
            )
    return problems


def _check_audit(
    canonical: Dict[str, Any], reproduced: Dict[str, Any]
) -> List[str]:
    problems: List[str] = []
    c_audit = canonical.get("audit", {})
    r_audit = reproduced.get("audit", {})
    for field in _AUDIT_FIELDS:
        expected = c_audit.get(field, "<absent>")
        actual = r_audit.get(field, "<absent>")
        if expected != actual:
            problems.append(
                f"audit mismatch: {field}: canonical={expected!r} reproduced={actual!r}"
            )
    return problems


def _check_ladder(
    canonical: Dict[str, Any], reproduced: Dict[str, Any]
) -> List[str]:
    """The ladder is an ordered ladder: reordering it changes the experiment."""
    problems: List[str] = []
    c_ladder = [entry.get("config") for entry in canonical.get("ladder", [])]
    r_ladder = [entry.get("config") for entry in reproduced.get("ladder", [])]
    if c_ladder != r_ladder:
        problems.append(
            "ladder config order differs:\n"
            f"  canonical:  {c_ladder}\n"
            f"  reproduced: {r_ladder}"
        )
    return problems


def _check_results(
    canonical: Dict[str, Any], reproduced: Dict[str, Any]
) -> List[str]:
    problems: List[str] = []

    c_rows = canonical.get("results", [])
    r_rows = reproduced.get("results", [])
    c_order = [row.get("config") for row in c_rows]
    r_order = [row.get("config") for row in r_rows]

    # The ladder walks from weakest to strongest capability, so the order in
    # which results are reported is part of the experiment. Compare it before
    # the per-config lookup, which would otherwise hide a reordering as "all
    # configs present and equal".
    if c_order != r_order:
        problems.append(
            "results config order differs:\n"
            f"  canonical:  {c_order}\n"
            f"  reproduced: {r_order}"
        )

    c_by_name = {name: row for name, row in zip(c_order, c_rows)}
    r_by_name = {name: row for name, row in zip(r_order, r_rows)}

    missing = [name for name in c_by_name if name not in r_by_name]
    extra = [name for name in r_by_name if name not in c_by_name]
    for name in missing:
        problems.append(f"missing config in reproduction: {name!r}")
    for name in extra:
        problems.append(f"unexpected extra config in reproduction: {name!r}")

    for name, c_row in c_by_name.items():
        r_row = r_by_name.get(name)
        if r_row is None:
            continue
        for field in _RESULT_FIELDS:
            expected = c_row.get(field, "<absent>")
            actual = r_row.get(field, "<absent>")
            if expected != actual:
                problems.append(
                    f"{name}: {field}: canonical={expected!r} reproduced={actual!r}"
                )
        # delta_vs_v03_provenance is derived, so it must match too.
        c_delta = c_row.get("delta_vs_v03_provenance", {})
        r_delta = r_row.get("delta_vs_v03_provenance", {})
        for key in sorted(set(c_delta) | set(r_delta)):
            expected = c_delta.get(key, "<absent>")
            actual = r_delta.get(key, "<absent>")
            if expected != actual:
                problems.append(
                    f"{name}: delta_vs_v03_provenance.{key}: "
                    f"canonical={expected!r} reproduced={actual!r}"
                )
    return problems


def _check_corpus_markers() -> List[str]:
    """Fail closed: a canonical comparison is meaningless with markers on."""
    raw = os.environ.get(_CORPUS_MARKERS_ENV)
    if raw is not None and raw.strip().lower() in _MARKER_VALUES_ON:
        return [
            f"{_CORPUS_MARKERS_ENV}={raw!r} enables corpus-specific markers, "
            "under which the engine scores differently. The canonical run was "
            "produced with the variable unset. Unset it and re-run."
        ]
    return []


def compare(
    canonical_path: Path, reproduced_path: Path
) -> Tuple[List[str], Dict[str, Any], Dict[str, Any]]:
    """Compare two artifacts. Returns (problems, canonical, reproduced)."""
    canonical = _load(canonical_path)
    reproduced = _load(reproduced_path)

    problems: List[str] = []
    problems.extend(_check_corpus_markers())
    problems.extend(_check_identity(canonical, reproduced))
    problems.extend(_check_audit(canonical, reproduced))
    problems.extend(_check_ladder(canonical, reproduced))
    problems.extend(_check_results(canonical, reproduced))
    return problems, canonical, reproduced


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("canonical", help="committed canonical artifact (JSON)")
    parser.add_argument("reproduced", help="freshly reproduced artifact (JSON)")
    args = parser.parse_args(argv)

    canonical_path = Path(args.canonical)
    reproduced_path = Path(args.reproduced)

    try:
        problems, canonical, reproduced = compare(canonical_path, reproduced_path)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: could not compare artifacts: {exc}", file=sys.stderr)
        return 2

    configs = len(canonical.get("results", []))
    sampling = canonical.get("sampling", "<absent>")

    if problems:
        print("FAIL: v0.4.1 reproduction does NOT match canonical artifact")
        print(f"  canonical:  {canonical_path}")
        print(f"  reproduced: {reproduced_path}")
        print(f"  {len(problems)} difference(s):")
        for problem in problems:
            print(f"    - {problem}")
        return 1

    print("PASS: v0.4.1 reproduction matches canonical artifact")
    print(f"configs: {configs}")
    print(f"sampling: {sampling}")
    print(f"audit rows: {canonical.get('audit', {}).get('rows', '<absent>')}")
    print(
        "audit trajectories: "
        f"{canonical.get('audit', {}).get('trajectories', '<absent>')}"
    )
    # An artifact with no results cannot have been compared against anything
    # meaningful, so refuse to report a pass on it.
    if not reproduced.get("results"):
        print(
            "ERROR: reproduction contains no results; refusing to report a pass",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

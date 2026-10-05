"""Aggregate Qoder evaluation runs into results.csv / summary.json / failure_cases.jsonl.

This tool READS graded results. It does not score, does not re-run anything,
and does not decide Task Success -- that is the grader's job, and its verdict
is carried through verbatim. Re-deriving a headline metric here would let two
components disagree about the same run.

Hard rules enforced below:

* The denominator comes from the frozen benchmark manifest and must be exactly
  8. Anything else is a hard failure -- silently aggregating over 7 tasks would
  publish a Task Success Rate measured against the wrong denominator.
* Only frozen task ids are accepted. A rejected or deferred task entering the
  set would inflate the denominator with work that was never part of the
  evaluation.
* A task whose grade.json is missing is MISSING, not successful and not a
  model failure. Both of those are claims about the agent, and there is no
  evidence either way.
* ``task_success`` must match the grader's own verdict. A mismatch means one of
  the two components is lying about the run, which must stop the aggregation.
* Baseline-relative regression is never re-interpreted. The grader already
  decided whether pre-existing failures count; this tool only reports that.

Usage:
    python aggregate.py                      # reads evaluation_runs/
    python aggregate.py --runs DIR --out DIR # explicit paths
    python aggregate.py --selfcheck          # run the synthetic fixtures
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

EVAL_ROOT = Path(__file__).resolve().parent
BENCH_ROOT = EVAL_ROOT.parent / "RealRepoBench-Q2609"

#: The frozen evaluation set for RealRepoBench-Q2609 v0.1.
EXPECTED_FROZEN_TASKS = 8

#: Tasks explicitly excluded from the formal denominator.
REJECTED_OR_DEFERRED = {"RB-EM-003", "RB-PS-001", "RB-PS-002", "RB-PS-003"}

#: Controlled failure taxonomy. Free-text categories cannot be compared across
#: tasks, so anything that does not map cleanly becomes UNKNOWN.
FAILURE_TAXONOMY = (
    "LOCALIZATION_FAILURE",
    "IMPLEMENTATION_FAILURE",
    "INCOMPLETE_FIX",
    "REGRESSION",
    "CONSTRAINT_VIOLATION",
    "TEST_GAMING",
    "TOOL_FAILURE",
    "ENVIRONMENT_FAILURE",
    "TIMEOUT",
    "UNKNOWN",
)

CSV_COLUMNS = [
    "task_id", "repository", "task_type", "capabilities", "difficulty",
    "execution_completed", "grade_completed",
    "functional_score", "hidden_score", "constraint_score", "regression_score",
    "total_score",
    "public_tests_pass", "hidden_tests_pass",
    "target_fix_pass", "regression_pass", "constraint_violation",
    "forbidden_files_unchanged",
    "task_success",
    "duration_seconds", "human_intervention_count", "files_modified_count",
    "failure_category", "failure_summary",
]


class AggregationError(RuntimeError):
    """A condition that must stop the aggregation rather than be worked around."""


# ─── frozen-set resolution ────────────────────────────────────────────────
def load_frozen_set(bench_root: Path = BENCH_ROOT) -> List[str]:
    """Read the frozen evaluation set out of the benchmark's own manifest.

    The manifest is the authority on what was frozen, so the denominator is
    never hard-coded twice.
    """
    manifest_path = bench_root / "benchmark_manifest.json"
    if not manifest_path.exists():
        raise AggregationError(f"benchmark manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if manifest.get("frozen") is not True:
        raise AggregationError(
            "benchmark manifest does not report frozen: true -- refusing to "
            "aggregate an unfrozen benchmark"
        )

    frozen_ids = [t["task_id"] for t in manifest.get("tasks", [])
                  if t.get("ready")]

    # Cross-check against the benchmark's own declaration so a manifest that
    # disagrees with the harness cannot quietly become the denominator.
    declared = frozen_set_from_harness(bench_root)
    if set(frozen_ids) != declared:
        raise AggregationError(
            f"manifest frozen set {sorted(frozen_ids)} disagrees with the "
            f"benchmark's declaration {sorted(declared)}"
        )

    if not frozen_ids:
        raise AggregationError("manifest reports no frozen tasks")

    if len(frozen_ids) != EXPECTED_FROZEN_TASKS:
        raise AggregationError(
            f"frozen denominator is {len(frozen_ids)}, expected "
            f"{EXPECTED_FROZEN_TASKS}: {frozen_ids}"
        )
    return sorted(frozen_ids)


def frozen_set_from_harness(bench_root: Path = BENCH_ROOT) -> set:
    """The frozen set exactly as the benchmark declares it.

    Parsed with ``ast`` rather than executed: the manifest module does
    module-level ``sys.path`` work and imports, none of which is needed to read
    a set literal, and executing someone else's module to read a constant is
    both fragile and unnecessary.
    """
    import ast

    path = bench_root / "harness" / "manifest.py"
    if not path.exists():
        raise AggregationError(f"benchmark frozen-set declaration not found: {path}")

    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "FROZEN_SET" in targets:
                return set(ast.literal_eval(node.value))
    raise AggregationError("benchmark does not declare FROZEN_SET")


# ─── input validation ─────────────────────────────────────────────────────
@dataclass
class GradeRecord:
    """One task's graded result, plus the run metadata around it."""

    task_id: str
    grade: Dict[str, Any]
    metadata: Dict[str, Any]
    run_dir: Path
    problems: List[str] = field(default_factory=list)

    @property
    def task_success(self) -> bool:
        return bool(self.grade.get("task_success"))

    @property
    def scores(self) -> Dict[str, Any]:
        return self.grade.get("scores", {})

    @property
    def baseline_relative(self) -> Dict[str, Any]:
        return self.grade.get("baseline_relative", {})


def read_run(run_dir: Path, frozen: set) -> Optional[GradeRecord]:
    """Load one run directory. Returns None when it does not hold a graded task."""
    grade_path = run_dir / "grade.json"
    if not grade_path.exists():
        return None

    try:
        grade = json.loads(grade_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise AggregationError(f"{run_dir.name}: grade.json is not valid JSON: {e}")

    task_id = grade.get("task_id") or run_dir.name
    problems: List[str] = []

    if task_id not in frozen:
        raise AggregationError(
            f"{task_id}: not in the frozen evaluation set "
            f"({sorted(frozen)}). Rejected or deferred tasks must never enter "
            f"the formal denominator."
        )

    metadata_path = run_dir / "metadata.json"
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise AggregationError(f"{run_dir.name}: metadata.json invalid: {e}")
    else:
        # Metadata is optional. Missing evidence is not evidence, so defaults
        # are neutral rather than flattering.
        metadata = {}
        problems.append("metadata.json missing; run-level evidence unavailable")

    return GradeRecord(task_id=task_id, grade=grade, metadata=metadata,
                       run_dir=run_dir, problems=problems)


def validate_grade(rec: GradeRecord) -> List[str]:
    """Schema and range checks on one graded result."""
    problems: List[str] = list(rec.problems)
    grade = rec.grade

    if "task_success" not in grade:
        problems.append("grade.json has no task_success field")
    if "scores" not in grade:
        problems.append("grade.json has no scores object")

    scores = grade.get("scores", {})
    for key, value in scores.items():
        if not isinstance(value, int) or value < 0:
            problems.append(f"score {key}={value!r} is not a non-negative int")
    total = scores.get("total")
    if isinstance(total, int) and not (0 <= total <= 100):
        problems.append(f"total_score {total} outside 0..100")

    # The headline verdict must be consistent with the components it is made of.
    if "task_success" in grade:
        declared = bool(grade["task_success"])
        recomputed = _recompute_success(grade)
        if declared != recomputed:
            problems.append(
                f"task_success={declared} disagrees with the grader's own "
                f"components ({recomputed})"
            )

    # Baseline-relative regression is the grader's call, not this tool's.
    rel = grade.get("baseline_relative", {})
    if "regression_pass" not in rel:
        problems.append("grade.json omits baseline_relative.regression_pass")

    interventions = rec.metadata.get("human_intervention_count")
    if interventions is not None and (not isinstance(interventions, int)
                                      or interventions < 0):
        problems.append(f"human_intervention_count={interventions!r} is negative")

    duration = rec.metadata.get("duration_seconds")
    if duration is not None and (not isinstance(duration, (int, float))
                                 or duration < 0):
        problems.append(f"duration_seconds={duration!r} is negative")

    return problems


def _recompute_success(grade: Dict[str, Any]) -> bool:
    """Independent re-derivation of Task Success from the grader's own output.

    Used only to CONFIRM the grader's verdict agrees with the fields it
    actually emits. It never replaces it: a disagreement stops the aggregation,
    because it means one of the two components is misreporting the run.

    Reads only what ``Score.to_dict()`` writes -- ``scores`` and
    ``baseline_relative``. Boolean pass/fail fields are NOT part of that output,
    so a check that depends on them would reject every genuine grader result.
    """
    scores = grade.get("scores", {})
    rel = grade.get("baseline_relative", {})

    # 60 functional requires BOTH public and hidden to pass.
    public_and_hidden = scores.get("functional_correctness") == 60
    # 20 hidden requires the hidden component to be earned.
    hidden_earned = (scores.get("hidden_tests") or 0) > 0
    no_violations = scores.get("constraint_compliance") == 10
    no_new_failure = rel.get("regression_pass", True) is not False
    target_cleared = rel.get("target_fix_pass", True) is not False

    return bool(public_and_hidden and hidden_earned and no_violations
                and no_new_failure and target_cleared)


# ─── failure classification ───────────────────────────────────────────────
def classify_failure(rec: GradeRecord) -> tuple[str, str]:
    """Map a failed run onto the controlled taxonomy.

    Ordered so the most specific cause wins: an agent that broke the build AND
    edited a frozen file is reported as a constraint violation, because that is
    the finding that cannot be excused.
    """
    scores = rec.scores
    rel = rec.baseline_relative
    metadata = rec.metadata

    if metadata.get("execution_error"):
        return "TOOL_FAILURE", str(metadata["execution_error"])
    if metadata.get("environment_error"):
        return "ENVIRONMENT_FAILURE", str(metadata["environment_error"])
    if metadata.get("timed_out"):
        return "TIMEOUT", "run exceeded its time budget"

    violations = scores.get("constraint_compliance")
    if violations == 0 or metadata.get("constraint_violation"):
        return "CONSTRAINT_VIOLATION", "a frozen or forbidden path was modified"

    if rel.get("regression_pass") is False:
        new = rel.get("new_failures", [])
        return "REGRESSION", (
            f"{len(new)} new failure(s) outside the baseline: "
            + ", ".join(map(str, new[:3]))
        )

    if metadata.get("test_gaming_suspected"):
        return "TEST_GAMING", "run shows signs of gaming the checks"

    # Derived the way the grader derives them: the 60-point functional
    # component requires BOTH public and hidden to pass, and the hidden
    # component is only earned when hidden checks actually pass. Because a
    # failing hidden component also zeroes functional, a hidden failure is the
    # more specific signal and is tested first.
    functional = rec.scores.get("functional_correctness")
    public_pass = functional == 60
    hidden_pass = (rec.scores.get("hidden_tests") or 0) > 0

    if hidden_pass is False and rel.get("target_fix_pass") is False:
        return "INCOMPLETE_FIX", (
            "the defect's observable failure is still present: "
            + ", ".join(map(str, rel.get("surviving_target_failures", [])[:3]))
        )
    if hidden_pass is False and public_pass is False:
        return "LOCALIZATION_FAILURE", "neither public nor hidden checks pass"
    if public_pass is False:
        return "IMPLEMENTATION_FAILURE", "public checks fail after the change"
    if hidden_pass is False:
        return "IMPLEMENTATION_FAILURE", "hidden checks fail after the change"
    if not metadata.get("grade_completed", True):
        return "TOOL_FAILURE", "grading did not complete"

    return "UNKNOWN", "; ".join(rec.grade.get("reasons", [])[:3]) or "no reasons recorded"


# ─── aggregation ──────────────────────────────────────────────────────────
def task_metadata(frozen: List[str],
                  bench_root: Path = BENCH_ROOT) -> Dict[str, Dict[str, Any]]:
    """Per-task descriptive metadata for the report columns.

    Prefers the benchmark manifest, then the task's own ``task.json``. Older
    tasks were built before ``task_type`` existed, so the manifest carries
    ``null`` for them; the per-task file often has it. Reading both is safe
    because neither is inside the frozen checksum set -- the snapshot's
    implementation files and tests are what is frozen.
    """
    manifest = json.loads((bench_root / "benchmark_manifest.json")
                          .read_text(encoding="utf-8"))
    info: Dict[str, Dict[str, Any]] = {
        t["task_id"]: dict(t) for t in manifest.get("tasks", [])
    }

    for tid in frozen:
        row = info.setdefault(tid, {})
        if row.get("task_type") and row.get("capabilities"):
            continue
        task_json = bench_root / "tasks" / tid / "task.json"
        if not task_json.exists():
            continue
        try:
            detail = json.loads(task_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        row.setdefault("task_type", detail.get("task_type"))
        row.setdefault("capabilities", detail.get("capabilities"))
        row.setdefault("repository", detail.get("repository"))
        row.setdefault("difficulty", detail.get("difficulty"))
        row.setdefault("category", detail.get("category"))
    return info


def _benchmark_identity(bench_root: Path = BENCH_ROOT) -> Dict[str, Any]:
    manifest = json.loads((bench_root / "benchmark_manifest.json")
                          .read_text(encoding="utf-8"))
    return {"benchmark": manifest.get("benchmark"),
            "version": manifest.get("version")}


def aggregate(runs_dir: Path, frozen: List[str],
              bench_root: Path = BENCH_ROOT) -> Dict[str, Any]:
    frozen_set = set(frozen)
    task_info = task_metadata(frozen, bench_root)

    seen: Dict[str, GradeRecord] = {}
    for run_dir in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
        rec = read_run(run_dir, frozen_set)
        if rec is None:
            continue
        if rec.task_id in seen:
            raise AggregationError(
                f"duplicate task_id {rec.task_id} in runs {seen[rec.task_id].run_dir} "
                f"and {run_dir}"
            )
        seen[rec.task_id] = rec

    duplicated_problems = {tid: validate_grade(rec) for tid, rec in seen.items()}
    schema_errors = {tid: p for tid, p in duplicated_problems.items() if p}
    for tid, problems in schema_errors.items():
        raise AggregationError(f"{tid}: invalid grade.json: {'; '.join(problems)}")

    graded_ids = sorted(seen)
    missing = [tid for tid in frozen if tid not in seen]
    successful = [tid for tid in graded_ids if seen[tid].task_success]

    rows = []
    for tid in frozen:
        info = task_info.get(tid, {})
        rec = seen.get(tid)
        if rec is None:
            rows.append(_missing_row(tid, info))
            continue
        rows.append(_build_row(tid, info, rec))

    failures = []
    for tid in graded_ids:
        if not seen[tid].task_success:
            category, summary = classify_failure(seen[tid])
            failures.append(_failure_record(tid, task_info.get(tid, {}),
                                            seen[tid], category, summary))

    graded = len(graded_ids)
    evaluation_complete = graded == len(frozen)

    def _pass_rate(predicate):
        if not graded:
            return None
        return round(sum(1 for i in graded_ids if predicate(seen[i])) / graded, 4)

    identity = _benchmark_identity(bench_root)
    summary = {
        "benchmark": identity["benchmark"],
        "version": identity["version"],
        "frozen_tasks": len(frozen),
        "evaluated_tasks": len(graded_ids),
        "graded_tasks": graded,
        "successful_tasks": len(successful),
        # A partial run must never be published as the final rate: the
        # denominator would silently be "whatever happened to finish".
        "task_success_rate": (
            round(len(successful) / len(frozen), 4) if evaluation_complete else None
        ),
        "evaluation_complete": evaluation_complete,
        "missing_tasks": missing,
    }

    if not evaluation_complete:
        summary["provisional_task_success_rate"] = (
            round(len(successful) / graded, 4) if graded else None
        )
        summary["provisional_note"] = (
            f"only {graded} of {len(frozen)} frozen tasks are graded, so this "
            f"is not the formal Task Success Rate"
        )

    summary.update({
        # "public pass" is the grader's 60-point functional component, which it
        # awards only when BOTH public and hidden pass.
        "public_test_pass_rate": _pass_rate(
            lambda r: r.scores.get("functional_correctness") == 60),
        "hidden_test_pass_rate": _pass_rate(
            lambda r: (r.scores.get("hidden_tests") or 0) > 0),
        "target_fix_rate": _rel_rate(seen, graded_ids, "target_fix_pass"),
        "regression_pass_rate": _rel_rate(seen, graded_ids, "regression_pass"),
        "constraint_violation_rate": _pass_rate(
            lambda r: r.scores.get("constraint_compliance") == 0),
        "mean_total_score": (
            round(statistics.fmean(
                [seen[i].scores.get("total", 0) for i in graded_ids]), 2)
            if graded else None
        ),
        # A median computed over the tasks that happen to have a duration
        # describes that subset, not the run. Report it only when coverage is
        # complete; otherwise state the coverage and leave the value null.
        "median_duration_seconds": (
            statistics.median([_duration(seen[i]) for i in graded_ids
                               if _duration(seen[i]) is not None])
            if all(_duration(seen[i]) is not None for i in graded_ids) and graded_ids
            else None
        ),
        "duration_coverage": (
            f"{sum(1 for i in graded_ids if _duration(seen[i]) is not None)}"
            f"/{len(frozen)}"
        ),
        "median_duration_status": (
            "NOT_AVAILABLE" if not all(
                _duration(seen[i]) is not None for i in graded_ids) or not graded_ids
            else "OK"
        ),
        # "total_" implies the whole frozen set, which is untrue at partial
        # coverage, so the field is named for what it actually is: the sum over
        # the tasks whose intervention count was recovered.
        "recorded_semantic_human_interventions": (
            sum(_interventions(seen[i]) for i in graded_ids)
            if graded_ids and all(
                _interventions(seen[i]) is not None for i in graded_ids) else None
        ),
        "semantic_intervention_coverage": (
            f"{sum(1 for i in graded_ids if _interventions(seen[i]) is not None)}"
            f"/{len(frozen)}"
        ),
        "semantic_intervention_coverage_note": (
            "The count covers only the tasks whose intervention count was "
            "recovered; it is not a whole-benchmark total."
        ),
        "by_repository": _group_rate(rows, "repository", graded),
        "by_task_type": _group_rate(rows, "task_type", graded),
    })

    # A task with no declared task_type is called out rather than quietly
    # bucketed: RB-AS-001 predates the task_type field, so a reader must not
    # mistake UNSPECIFIED for a real category. Detected from the task's own
    # metadata rather than from the normalised row label.
    unspecified = sorted(
        tid for tid, info_row in task_info.items()
        if tid in seen and not info_row.get("task_type")
    )
    if unspecified:
        summary["tasks_without_declared_task_type"] = unspecified

    return {"rows": rows, "summary": summary, "failures": failures,
            "missing": missing, "graded_ids": graded_ids}


def _rel_rate(seen, ids, key):
    if not ids:
        return None
    vals = [seen[i].baseline_relative.get(key) for i in ids]
    known = [v for v in vals if v is not None]
    if not known:
        return None
    return round(sum(1 for v in known if v is True) / len(known), 4)


def _rel_rate(seen, ids, key):
    if not ids:
        return None
    vals = [seen[i].baseline_relative.get(key) for i in ids]
    known = [v for v in vals if v is not None]
    if not known:
        return None
    return round(sum(1 for v in known if v is True) / len(known), 4)


def _group_rate(rows, key, graded):
    out: Dict[str, Any] = {}
    if not graded:
        return out
    for row in rows:
        if row["task_success"] is None:
            continue
        # Normalise an undeclared value so the grouping key is readable and
        # the buckets still cover every graded task.
        label = row[key] or "UNSPECIFIED"
        bucket = out.setdefault(label, {"graded": 0, "successful": 0})
        bucket["graded"] += 1
        bucket["successful"] += 1 if row["task_success"] else 0
    for bucket in out.values():
        bucket["task_success_rate"] = (
            round(bucket["successful"] / bucket["graded"], 4)
            if bucket["graded"] else None
        )
    return out


def _duration(rec: GradeRecord):
    d = rec.metadata.get("duration_seconds")
    return d if isinstance(d, (int, float)) and d >= 0 else None


def _interventions(rec: GradeRecord) -> Optional[int]:
    n = rec.metadata.get("human_intervention_count")
    return n if isinstance(n, int) and n >= 0 else None


def _missing_row(task_id: str, info: Dict[str, Any]) -> Dict[str, Any]:
    """An ungraded task is absent, not successful and not a model failure."""
    row = {col: None for col in CSV_COLUMNS}
    row.update({
        "task_id": task_id,
        "repository": info.get("repository"),
        "task_type": info.get("task_type") or "UNSPECIFIED",
        "capabilities": "; ".join(info.get("capabilities", []) or []),
        "difficulty": info.get("difficulty"),
        "execution_completed": False,
        "grade_completed": False,
        "failure_category": "MISSING",
        "failure_summary": "no graded result present for this frozen task",
    })
    return row


def _build_row(task_id: str, info: Dict[str, Any],
               rec: GradeRecord) -> Dict[str, Any]:
    scores = rec.scores
    rel = rec.baseline_relative
    md = rec.metadata
    functional = scores.get("functional_correctness")
    return {
        "task_id": task_id,
        "repository": info.get("repository"),
        "task_type": info.get("task_type") or "UNSPECIFIED",
        "capabilities": "; ".join(info.get("capabilities", []) or []) or "UNSPECIFIED",
        "difficulty": info.get("difficulty"),
        "execution_completed": md.get("execution_completed", True),
        "grade_completed": md.get("grade_completed", True),
        "functional_score": functional,
        "hidden_score": scores.get("hidden_tests"),
        "constraint_score": scores.get("constraint_compliance"),
        "regression_score": scores.get("no_regression"),
        "total_score": scores.get("total"),
        # Derived from the grader's component scores: 60 functional means both
        # public and hidden passed, which is exactly how the grader defines it.
        "public_tests_pass": functional == 60,
        "hidden_tests_pass": (scores.get("hidden_tests") or 0) > 0,
        "target_fix_pass": rel.get("target_fix_pass"),
        "regression_pass": rel.get("regression_pass"),
        "constraint_violation": scores.get("constraint_compliance") == 0,
        "forbidden_files_unchanged": scores.get("constraint_compliance") == 10,
        # Verbatim from the grader; never recomputed here.
        "task_success": rec.task_success,
        "duration_seconds": md.get("duration_seconds"),
        # Absent means unknown, not zero: only a present 0 may read as none.
        "human_intervention_count": (
            md["human_intervention_count"]
            if isinstance(md.get("human_intervention_count"), int) else None
        ),
        "files_modified_count": md.get("files_modified_count"),
        "failure_category": ("" if rec.task_success else classify_failure(rec)[0]),
        "failure_summary": ("" if rec.task_success else classify_failure(rec)[1]),
    }


def _failure_record(task_id, info, rec, category, summary):
    scores = rec.scores
    rel = rec.baseline_relative
    functional = scores.get("functional_correctness")
    return {
        "task_id": task_id,
        "repository": info.get("repository"),
        "task_type": info.get("task_type") or "UNSPECIFIED",
        "total_score": scores.get("total"),
        "public_tests_pass": functional == 60,
        "hidden_tests_pass": (scores.get("hidden_tests") or 0) > 0,
        "target_fix_pass": rel.get("target_fix_pass"),
        "regression_pass": rel.get("regression_pass"),
        "constraint_violation": scores.get("constraint_compliance") == 0,
        "human_intervention_count": _interventions(rec),  # None when unrecoverable
        "failure_category": category,
        "failure_summary": summary,
    }


# ─── writers ──────────────────────────────────────────────────────────────
def write_outputs(result: Dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / "results.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in result["rows"]:
            writer.writerow(row)

    (out_dir / "summary.json").write_text(
        json.dumps(result["summary"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")

    with open(out_dir / "failure_cases.jsonl", "w", encoding="utf-8") as f:
        for rec in result["failures"]:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    (out_dir / "AGGREGATION_REPORT.md").write_text(
        _qa_report(result), encoding="utf-8")

    print(f"results -> {csv_path}")
    print(f"summary -> {out_dir / 'summary.json'}")
    print(f"failures -> {out_dir / 'failure_cases.jsonl'}")


def _qa_report(result: Dict[str, Any]) -> str:
    s = result["summary"]
    lines = [
        "# Aggregation QA report (internal)",
        "",
        f"- denominator: **{s['frozen_tasks']}**",
        f"- evaluation runs found: {s['evaluated_tasks']}",
        f"- graded: {s['graded_tasks']}",
        f"- successful: {s['successful_tasks']}",
        f"- missing: {', '.join(s['missing_tasks']) or 'none'}",
        f"- evaluation_complete: **{s['evaluation_complete']}**",
        f"- task_success_rate: {s['task_success_rate']}",
        "",
        "## Publishable?",
        "",
    ]
    publishable = s["evaluation_complete"] and not s["missing_tasks"]
    lines.append(
        "YES -- all frozen tasks are graded and the denominator is 8."
        if publishable else
        f"NO -- {len(s['missing_tasks'])} frozen task(s) are ungraded "
        f"({', '.join(s['missing_tasks'])}). Publishing now would understate "
        f"the denominator."
    )
    return "\n".join(lines) + "\n"


# ─── CLI ──────────────────────────────────────────────────────────────────
def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", type=Path, default=EVAL_ROOT / "evaluation_runs")
    ap.add_argument("--out", type=Path, default=EVAL_ROOT / "results")
    args = ap.parse_args(argv)

    try:
        frozen = load_frozen_set()
        harness_set = frozen_set_from_harness()
        if set(frozen) != harness_set:
            raise AggregationError(
                f"manifest frozen set {frozen} disagrees with the harness "
                f"declaration {sorted(harness_set)}"
            )
        result = aggregate(args.runs, frozen)
    except AggregationError as e:
        print(f"AGGREGATION REFUSED: {e}", file=sys.stderr)
        return 2

    write_outputs(result, args.out)
    if not result["summary"]["evaluation_complete"]:
        print(
            "NOTE: evaluation is incomplete; the formal task_success_rate is "
            "null by design.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

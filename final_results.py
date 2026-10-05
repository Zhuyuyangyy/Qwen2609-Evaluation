"""Build the final submission result files from the archived evidence.

Read-only with respect to the evidence. Every number is derived from the
archived ``grade.json`` / ``metadata.json``; nothing is inferred and nothing is
padded. A field that cannot be established from an artifact is written as
``null`` or ``NOT_AVAILABLE`` rather than estimated.

Three metric families are computed separately and are never merged:

* benchmark execution  -- denominator 8, how many produced a valid submission
* model performance    -- denominator valid runs ONLY
* harness reliability  -- denominator 8

    python final_results.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

EVAL_ROOT = Path(__file__).resolve().parent
BENCH = EVAL_ROOT.parent / "RealRepoBench-Q2609"
RUNS = EVAL_ROOT / "evaluation_runs"

ORDERED = [
    "RB-AS-001", "RB-AS-002", "RB-AS-003", "RB-AS-004", "RB-AS-005",
    "RB-EM-001", "RB-EM-002", "RB-EM-004",
]

COLUMNS = [
    "task_id", "repository", "task_type", "capabilities", "difficulty",
    "run_status", "valid_model_submission",
    "task_success", "total_score",
    "functional_score", "hidden_score", "constraint_score", "regression_score",
    "target_fix_pass", "regression_pass", "constraint_violation",
    "manual_resume_count", "harness_runtime_error_count",
    "duration_seconds", "files_modified_count",
]


def _read(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _task_spec(task_id: str) -> Dict[str, Any]:
    for line in (BENCH / "tasks.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            if r["task_id"] == task_id:
                return r
    return {}


def build_rows() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for tid in ORDERED:
        meta = _read(RUNS / tid / "metadata.json") or {}
        grade = _read(RUNS / tid / "grade.json")
        spec = _task_spec(tid)
        graded = grade is not None and grade.get("task_success") is not None

        scores = (grade or {}).get("scores", {})
        rel = (grade or {}).get("baseline_relative", {})

        # A correct submission may legitimately touch non-.py files, so
        # "files modified" comes from the recorded metadata, and the .py count
        # is reported separately as the implementation-change signal.
        rows.append({
            "task_id": tid,
            "repository": spec.get("repository", "NOT_AVAILABLE"),
            "task_type": spec.get("task_type") or "UNSPECIFIED",
            "capabilities": "; ".join(spec.get("capabilities") or []) or "UNSPECIFIED",
            "difficulty": spec.get("difficulty", "NOT_AVAILABLE"),
            "run_status": meta.get("run_status", "NOT_RUN"),
            "valid_model_submission": meta.get("run_status") == "VALID_SUBMISSION",
            "task_success": (grade.get("task_success") if graded else None),
            "total_score": scores.get("total"),
            "functional_score": scores.get("functional_correctness"),
            "hidden_score": scores.get("hidden_tests"),
            "constraint_score": scores.get("constraint_compliance"),
            "regression_score": scores.get("no_regression"),
            "target_fix_pass": rel.get("target_fix_pass"),
            "regression_pass": rel.get("regression_pass"),
            "constraint_violation": (
                scores.get("constraint_compliance") == 0
                if graded else None
            ),
            "manual_resume_count": meta.get("manual_resume_count"),
            "harness_runtime_error_count": meta.get("harness_runtime_error_count"),
            "duration_seconds": meta.get("duration_seconds"),
            "files_modified_count": meta.get("files_modified_count"),
        })
    return rows


def compute_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    valid = [r for r in rows if r["run_status"] == "VALID_SUBMISSION"]
    infra = [r for r in rows if r["run_status"] == "INFRASTRUCTURE_FAILURE"]
    not_run = [r for r in rows if r["run_status"] == "NOT_RUN"]
    invalid = [r for r in rows if r["run_status"] == "INVALID_RUN"]

    valid_runs = len(valid)
    successes = sum(1 for r in valid if r["task_success"] is True)
    perfect = sum(1 for r in valid if r["total_score"] == 100)

    # A count of null means UNRECOVERABLE, not zero. Treating unknown as zero
    # would manufacture a "needed no manual resume" statistic out of missing
    # evidence, so only tasks with a recovered 0 may be counted as zero-resume.
    resume_recovered = [r for r in rows
                        if isinstance(r["manual_resume_count"], int)]
    resume_unrecovered = [r["task_id"] for r in rows
                          if r["manual_resume_count"] is None]
    resume_tasks = [r["task_id"] for r in resume_recovered
                    if r["manual_resume_count"] > 0]
    resume_total = sum(r["manual_resume_count"] for r in resume_recovered)
    err_recovered = [r for r in rows
                     if isinstance(r["harness_runtime_error_count"], int)]
    err_tasks = [r["task_id"] for r in err_recovered
                 if r["harness_runtime_error_count"] > 0]
    # Only a task with a RECOVERED count of 0 may be called zero-resume.
    zero_resume = sum(1 for r in valid if r["manual_resume_count"] == 0)

    total = len(rows)
    return {
        "benchmark": "RealRepoBench-Q2609",
        "version": "0.1",
        "model": "qwen-latest-series-invite-2609",
        "harness": "Qoder",

        # -- A. benchmark execution (denominator 8) --
        "benchmark_tasks": total,
        "valid_model_submissions": valid_runs,
        "valid_model_successes": successes,
        "infrastructure_failures": len(infra),
        "not_run": len(not_run),
        "invalid_runs": len(invalid),

        # -- B. model performance (denominator valid runs ONLY) --
        "valid_run_task_success_rate": (
            round(successes / valid_runs, 4) if valid_runs else None
        ),
        "valid_run_scope_note": (
            "Denominator is valid model runs only. This is NOT the 8-task "
            "Task Success Rate."
        ),

        # -- C. harness reliability (denominator 8) --
        "harness_valid_submission_rate": round(valid_runs / total, 4),
        # Counts are over RECOVERED values only, and the names say so: a bare
        # "manual_resume_task_count" reads as "0 across all 8 tasks", which is
        # exactly the unknown-as-zero mistake this field naming exists to stop.
        "confirmed_manual_resume_task_count": len(resume_tasks),
        "confirmed_manual_resume_task_ids": resume_tasks,
        "manual_resume_total_count": resume_total,
        "manual_resume_count_coverage": f"{len(resume_recovered)}/{total}",
        "manual_resume_count_status": (
            "COMPLETE" if len(resume_recovered) == total else "PARTIAL_COVERAGE"
        ),
        "manual_resume_unrecoverable_tasks": resume_unrecovered,
        "manual_resume_unrecoverable_count": len(resume_unrecovered),
        "manual_resume_scope_note": (
            f"Only {len(resume_recovered)}/{total} tasks have a recovered "
            f"manual_resume_count; the rest are unrecoverable and are NOT "
            f"counted as zero."
        ),
        "confirmed_runtime_error_task_count": len(err_tasks),
        "confirmed_runtime_error_task_ids": err_tasks,
        "runtime_error_count_coverage": f"{len(err_recovered)}/{total}",
        "runtime_error_count_status": (
            "COMPLETE" if len(err_recovered) == total else "PARTIAL_COVERAGE"
        ),
        "runtime_error_unrecoverable_tasks": [
            r["task_id"] for r in rows
            if r["harness_runtime_error_count"] is None
        ],
        # A rate over 8 would treat the unrecoverable tasks as failures of a
        # test they were never measured on. So the rate itself is null, and only
        # the raw counts are published.
        "confirmed_zero_resume_tasks": zero_resume,
        "resume_count_known_tasks": len(resume_recovered),
        "resume_count_unknown_tasks": len(resume_unrecovered),
        "zero_resume_autonomous_completion_rate": None,
        "zero_resume_rate_status": "NOT_AVAILABLE",
        "zero_resume_rate_note": (
            f"NOT_AVAILABLE. Only {len(resume_recovered)} of {total} tasks have "
            f"a recovered manual_resume_count ({zero_resume} of them zero); "
            f"{len(resume_unrecovered)} tasks' counts are unrecoverable. A "
            f"denominator of {total} would score the unknown tasks as if they "
            f"had been measured, so no rate is published."
        ),

        # -- protocol completeness --
        "evaluation_complete_under_original_protocol": valid_runs == total,
        "original_8_task_tsr_available": valid_runs == total,
        "original_8_task_tsr": (
            round(successes / total, 4) if valid_runs == total else None
        ),

        # -- ceiling-effect facts (facts only, no capability claim) --
        "ceiling_effect_facts": {
            "valid_run_n": valid_runs,
            "valid_run_successes": successes,
            "perfect_scores_among_valid_runs": perfect,
            "correctness_failures_among_valid_runs": valid_runs - successes,
            "observed": valid_runs == successes,
        },

        "duration_coverage": {
            "tasks_with_duration": sum(1 for r in rows
                                       if isinstance(r["duration_seconds"], (int, float))),
            "tasks_total": total,
            "tasks_without_duration": [
                r["task_id"] for r in rows
                if not isinstance(r["duration_seconds"], (int, float))
            ],
            "median_duration_seconds": None,
            "median_duration_note": (
                "NOT_AVAILABLE. Duration was recorded for a minority of tasks, "
                "so no representative median is reported; a statistic computed "
                "on that subset would describe the subset, not the run."
            ),
        },
        "metrics_not_available": {
            "manual_resume_count_per_task_unrecoverable": [
                r["task_id"] for r in rows if r["manual_resume_count"] is None
            ],
            "harness_runtime_error_count_unrecoverable": [
                r["task_id"] for r in rows
                if r["harness_runtime_error_count"] is None
            ],
            "duration_unrecoverable": [
                r["task_id"] for r in rows if r["duration_seconds"] is None
            ],
        },
    }


def write_csv(rows: List[Dict[str, Any]], path: Path) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def write_task_table(rows: List[Dict[str, Any]]) -> str:
    lines = [
        "# Task results — RealRepoBench-Q2609 v0.1",
        "",
        "One row per frozen task. `null` / `NOT_AVAILABLE` means the artifact",
        "did not establish the value; it was not estimated.",
        "",
        "| task_id | repository | task_type | diff | run_status | valid | success | total | target_fix | regression_pass | constraint_violation | resume | duration_s | files |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---:|---:|---:|",
    ]
    for r in rows:
        def _b(v):
            return "yes" if v is True else ("no" if v is False else "—")
        def _n(v):
            return "n/a" if v is None else str(v)
        lines.append(
            f"| {r['task_id']} | {r['repository']} | {r['task_type']} "
            f"| {r['difficulty']} | {r['run_status']} | {_b(r['valid_model_submission'])} "
            f"| {_b(r['task_success'])} | {_n(r['total_score'])} "
            f"| {_b(r['target_fix_pass'])} | {_b(r['regression_pass'])} "
            f"| {_b(r['constraint_violation'])} | {_n(r['manual_resume_count'])} "
            f"| {_n(r['duration_seconds'])} | {_n(r['files_modified_count'])} |"
        )
    lines += [
        "",
        "## Reading this table",
        "",
        "- `run_status = INFRASTRUCTURE_FAILURE` means no stable model",
        "  submission existed. Its `task_success` is `null`, **not** `false`,",
        "  and it is excluded from the model denominator.",
        "- `task_type = UNSPECIFIED` is retained truthfully: RB-AS-001 was built",
        "  before the task_type and capabilities fields existed.",
        "- `duration_s = n/a` means the value could not be recovered from the",
        "  archived metadata and was not guessed.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    rows = build_rows()
    metrics = compute_metrics(rows)

    out = EVAL_ROOT / "FINAL_RESULTS_DATA"
    out.mkdir(exist_ok=True)
    (out / "FINAL_METRICS.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_csv(rows, out / "FINAL_RESULTS_TABLE.csv")
    (out / "TASK_RESULT_TABLE.md").write_text(
        write_task_table(rows), encoding="utf-8")

    print(f"benchmark_tasks            {metrics['benchmark_tasks']}")
    print(f"valid_model_submissions    {metrics['valid_model_submissions']}")
    print(f"valid_model_successes      {metrics['valid_model_successes']}")
    print(f"infrastructure_failures    {metrics['infrastructure_failures']}")
    print(f"valid_run_TSR              {metrics['valid_run_task_success_rate']}")
    print(f"harness_valid_sub_rate     {metrics['harness_valid_submission_rate']}")
    print(f"confirmed_manual_resume    {metrics['confirmed_manual_resume_task_count']} "
          f"(coverage {metrics['manual_resume_count_coverage']}, "
          f"{metrics['manual_resume_count_status']})")
    print(f"zero_resume_rate           {metrics['zero_resume_autonomous_completion_rate']} "
          f"(confirmed={metrics['confirmed_zero_resume_tasks']}, "
          f"known={metrics['resume_count_known_tasks']}, "
          f"unknown={metrics['resume_count_unknown_tasks']})")
    print(f"original_8_task_tsr        {metrics['original_8_task_tsr']}")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Build EVALUATION_STATUS.json with model and harness metrics kept apart.

Two rates are reported and they are not interchangeable:

* ``valid_run_task_success_rate`` is the model's performance, measured ONLY over
  valid model runs. It is not a statement about the 8-task benchmark, because a
  harness failure means there was no model output to judge.
* ``harness_valid_submission_rate`` and ``zero_resume_autonomous_completion_rate``
  measure the harness, and their denominator is 8.

An infrastructure failure is never counted as a model failure, and a task that
simply was not run is never counted as either.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

EVAL_ROOT = Path(__file__).resolve().parent
RUNS = EVAL_ROOT / "evaluation_runs"

BENCHMARK_TASKS = 8
ORDERED = [
    "RB-AS-001", "RB-AS-002", "RB-AS-003", "RB-AS-004", "RB-AS-005",
    "RB-EM-001", "RB-EM-002", "RB-EM-004",
]


def _load(tid: str) -> Dict[str, Any]:
    meta = RUNS / tid / "metadata.json"
    grade = RUNS / tid / "grade.json"
    m = json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {}
    g = (json.loads(grade.read_text(encoding="utf-8"))
         if grade.exists() else None)
    return m, g


def main() -> int:
    per_task: List[Dict[str, Any]] = []
    for tid in ORDERED:
        m, g = _load(tid)
        graded = g is not None and g.get("task_success") is not None
        per_task.append({
            "task_id": tid,
            "run_status": m.get("run_status", "NOT_RUN"),
            "valid_model_submission": m.get("valid_model_submission", False),
            "graded": graded,
            "task_success": (g.get("task_success") if graded else None),
            "total_score": (g.get("scores", {}).get("total") if graded else None),
            "manual_resume_count": m.get("manual_resume_count"),
            "harness_runtime_error_count": m.get("harness_runtime_error_count"),
        })

    valid = [t for t in per_task if t["run_status"] == "VALID_SUBMISSION"]
    infra = [t for t in per_task if t["run_status"] == "INFRASTRUCTURE_FAILURE"]
    not_run = [t for t in per_task if t["run_status"] == "NOT_RUN"]
    invalid = [t for t in per_task if t["run_status"] == "INVALID_RUN"]

    valid_runs = len(valid)
    successes = sum(1 for t in valid if t["task_success"] is True)

    # A recovered 0 counts; an unrecoverable count is never read as zero.
    resume_nums = [t["manual_resume_count"] for t in per_task
                   if isinstance(t["manual_resume_count"], int)]
    resume_unknown = [t["task_id"] for t in per_task
                      if t["manual_resume_count"] is None]
    resume_tasks = [t["task_id"] for t in per_task
                    if isinstance(t["manual_resume_count"], int)
                    and t["manual_resume_count"] > 0]
    runtime_error_tasks = [t["task_id"] for t in per_task
                           if isinstance(t["harness_runtime_error_count"], int)
                           and t["harness_runtime_error_count"] > 0]
    zero_resume_valid = sum(
        1 for t in valid if t["manual_resume_count"] == 0)

    status = {
        "benchmark": "RealRepoBench-Q2609",
        "version": "0.1",
        "model": "qwen-latest-series-invite-2609",
        "harness": "Qoder",

        # ── A. benchmark execution ──
        "benchmark_tasks": BENCHMARK_TASKS,
        "valid_model_runs": valid_runs,
        # Same key name as FINAL_METRICS.json, so a cross-file comparison is a
        # plain equality rather than a name mapping.
        "valid_model_submissions": valid_runs,
        "model_successes": successes,
        "infrastructure_failures": len(infra),
        "not_run": len(not_run),
        "invalid_runs": len(invalid),
        "infrastructure_failure_tasks": [t["task_id"] for t in infra],
        "not_run_tasks": [t["task_id"] for t in not_run],
        "invalid_run_tasks": [t["task_id"] for t in invalid],

        # ── B. model performance (only over valid runs) ──
        "valid_run_task_success_rate": (
            round(successes / valid_runs, 4) if valid_runs else None
        ),
        "valid_run_scope_note": (
            "measured over valid model runs only; it is NOT the 8-task TSR"
        ),

        # ── C. harness reliability (denominator is 8) ──
        # Same "confirmed_" naming as FINAL_METRICS.json, so a reader of either
        # file cannot mistake a partial-coverage count for a whole-set one.
        "confirmed_manual_resume_task_count": len(resume_tasks),
        "manual_resume_count_coverage": f"{len(resume_nums)}/{BENCHMARK_TASKS}",
        "manual_resume_count_status": (
            "COMPLETE" if len(resume_nums) == BENCHMARK_TASKS else "PARTIAL_COVERAGE"),
        "confirmed_manual_resume_task_ids": resume_tasks,
        "manual_resume_total_count": sum(resume_nums),
        "manual_resume_count_unknown_tasks": resume_unknown,
        "confirmed_zero_resume_tasks": zero_resume_valid,
        "resume_count_known_tasks": len(resume_nums),
        "resume_count_unknown_tasks": len(resume_unknown),
        # Same missingness semantics as FINAL_METRICS.json: a denominator of 8
        # would score tasks that were never measured, so the rate is null.
        "zero_resume_autonomous_completion_rate": None,
        "zero_resume_rate_status": "NOT_AVAILABLE",
        "confirmed_runtime_error_task_count": len(runtime_error_tasks),
        "runtime_error_count_coverage": f"{sum(1 for x in per_task if isinstance(x['harness_runtime_error_count'], int))}/{BENCHMARK_TASKS}",
        "runtime_error_count_status": (
            "COMPLETE" if all(isinstance(x["harness_runtime_error_count"], int) for x in per_task) else "PARTIAL_COVERAGE"),
        "confirmed_runtime_error_task_ids": runtime_error_tasks,
        "infrastructure_failure_tasks_count": len(infra),
        "harness_valid_submission_rate": round(valid_runs / BENCHMARK_TASKS, 4),

        # ── protocol completeness ──
        "evaluation_complete_under_original_protocol": (
            valid_runs == BENCHMARK_TASKS
        ),
        "incomplete_reason": (
            None if valid_runs == BENCHMARK_TASKS else
            f"{len(infra) + len(not_run)} of {BENCHMARK_TASKS} tasks have no "
            f"valid model submission, so no 8-task Task Success Rate exists"
        ),
        "tasks": per_task,
    }

    out = EVAL_ROOT / "EVALUATION_STATUS.json"
    out.write_text(json.dumps(status, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(json.dumps({k: v for k, v in status.items() if k != "tasks"},
                     indent=2, ensure_ascii=False))
    print(f"\nwritten to {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

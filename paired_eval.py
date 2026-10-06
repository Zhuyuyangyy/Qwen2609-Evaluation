"""Paired-model evaluation scaffolding for RealRepoBench-Q2609 v0.1.

The v0.1 run measured one model. The research value of the benchmark comes from
running a *second* model against the same frozen workspaces, the same hidden
checks and the same grader, so the comparison is paired rather than an
apple-to-orange reading of two report sections.

This module does NOT run a model and does NOT touch the frozen set. It provides:

* the run-directory convention a runner must produce;
* `plan`   — list the 8 frozen tasks with their workspace and prompt paths;
* `collect`— build a per-model coverage-aware summary from that model's runs;
* `compare`— put two models side by side, refusing to compare a field whose
              observation coverage differs, because a model that recorded its
              telemetry and a model that did not are not comparable on that
              field.

    python paired_eval.py plan
    python paired_eval.py collect --model qwen2609 --runs runs/qwen2609
    python paired_eval.py compare --model a --runs runs/a --against b --against-runs runs/b
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from coverage_schema import normalise_record, summarise  # noqa: E402

EVAL_ROOT = Path(__file__).resolve().parent
BENCH = EVAL_ROOT.parent / "RealRepoBench-Q2609"
WORKSPACES = EVAL_ROOT / "workspaces"

FROZEN_SET = [
    "RB-AS-001", "RB-AS-002", "RB-AS-003", "RB-AS-004", "RB-AS-005",
    "RB-EM-001", "RB-EM-002", "RB-EM-004",
]

#: What a runner must place under runs/<model>/<TASK_ID>/ for a run to count.
REQUIRED_ARTIFACTS = ("metadata.json", "patch.diff", "grade.json")

#: Optional but expected when the harness produces them.
OPTIONAL_ARTIFACTS = ("terminal.log", "public_test.log", "interventions.log")


def plan() -> Dict[str, Any]:
    """The fixed task list, with where each task's inputs live."""
    tasks = []
    for tid in FROZEN_SET:
        ws = WORKSPACES / tid
        tasks.append({
            "task_id": tid,
            "workspace": str(ws),
            "prompt": str(ws / "prompt.md"),
            "snapshot": str(ws / "repo_snapshot"),
            "public_tests": str(ws / "public_tests"),
            "fresh_session_required": True,
            # The embargoed checks live in the frozen benchmark and must never
            # be copied into a workspace.
            "hidden_tests": str(BENCH / "tasks" / tid / "hidden_tests"),
        })
    return {"benchmark": "RealRepoBench-Q2609", "version": "0.1",
            "frozen_tasks": len(tasks), "tasks": tasks}


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def collect(model: str, run_root: Path) -> Dict[str, Any]:
    """Coverage-aware per-model summary over that model's runs.

    A run counts as a valid model submission only when it produced a graded
    result. A task with a metadata file but no grade is an infrastructure
    failure: counting it as valid would inflate the submission rate, which is
    exactly the error the v0.1 report avoided.
    """
    root = Path(run_root)
    graded, missing, infra = [], [], []

    for tid in FROZEN_SET:
        run = root / tid
        meta_path = run / "metadata.json"
        if not meta_path.exists():
            missing.append(tid)
            continue
        meta = _load(meta_path)
        grade_path = run / "grade.json"
        if grade_path.exists():
            graded.append({
                "task_id": tid,
                "meta": meta,
                "grade": _load(grade_path),
            })
        elif meta.get("run_status") == "INFRASTRUCTURE_FAILURE":
            infra.append(tid)
        else:
            infra.append(tid)

    if not graded and not infra:
        return {"model": model, "error": "no runs found", "missing": missing}

    records = [normalise_record(g["meta"]) for g in graded]
    grades = [g["grade"] for g in graded]
    successes = [g for g in grades if g.get("task_success") is True]

    # Telemetry is summarised over graded runs only: an infrastructure failure
    # has no executed session, so its telemetry is not a sample of the harness.
    summary = summarise(records) if records else None

    return {
        "model": model,
        "benchmark_tasks": len(FROZEN_SET),
        "graded_tasks": len(graded),
        "task_successes": len(successes),
        # Denominator is this model's graded tasks; it is not the frozen 8.
        "valid_run_task_success_rate": (
            round(len(successes) / len(graded), 4) if graded else None
        ),
        # Denominator is the frozen 8. An infrastructure failure is NOT a valid
        # model submission, so it lowers this rate rather than raising it.
        "harness_valid_submission_rate": round(len(graded) / len(FROZEN_SET), 4),
        "infrastructure_failures": len(infra),
        "infrastructure_failure_tasks": infra,
        "missing_tasks": missing,
        "telemetry": summary,
    }


def compare(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """Put two models side by side, field by field.

    A telemetry field is marked comparable only when BOTH models observed it on
    the same set of tasks. Comparing a measured field against an unmeasured one
    would manufacture a difference that is really a difference in record
    keeping.
    """
    rows: Dict[str, Any] = {}
    a_name, b_name = a["model"], b["model"]
    for field in ("manual_resume", "runtime_error",
                  "semantic_human_intervention", "duration"):
        fa = a.get("telemetry", {}).get("fields", {}).get(field, {})
        fb = b.get("telemetry", {}).get("fields", {}).get(field, {})
        same_coverage = fa.get("coverage") == fb.get("coverage")
        both_complete = (fa.get("coverage_status") == "COMPLETE"
                         and fb.get("coverage_status") == "COMPLETE")
        rows[field] = {
            f"{a_name}_coverage": fa.get("coverage"),
            f"{b_name}_coverage": fb.get("coverage"),
            "comparable": bool(both_complete),
            "note": (
                "both models fully observed this field"
                if both_complete else
                ("coverage differs between models" if not same_coverage
                 else "neither/partial coverage; no comparison published")
            ),
        }
        if both_complete:
            rows[field][f"{a_name}_value"] = fa.get("value")
            rows[field][f"{b_name}_value"] = fb.get("value")

    return {
        "benchmark": "RealRepoBench-Q2609 v0.1",
        "models": [a_name, b_name],
        "task_success": {
            a_name: a.get("valid_run_task_success_rate"),
            b_name: b.get("valid_run_task_success_rate"),
        },
        "harness_valid_submission_rate": {
            a_name: a.get("harness_valid_submission_rate"),
            b_name: b.get("harness_valid_submission_rate"),
        },
        "telemetry": rows,
        "caveat": (
            "A rate is comparable only when both models graded the same tasks; "
            "check each model's graded_tasks before quoting the difference."
        ),
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan")

    p_c = sub.add_parser("collect")
    p_c.add_argument("--model", required=True)
    p_c.add_argument("--runs", type=Path, required=True)

    p_m = sub.add_parser("compare")
    p_m.add_argument("--model", required=True)
    p_m.add_argument("--runs", type=Path, required=True)
    p_m.add_argument("--against", required=True)
    p_m.add_argument("--against-runs", type=Path, required=True)

    args = ap.parse_args(argv)

    if args.cmd == "plan":
        p = plan()
        print(json.dumps(p, indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "collect":
        print(json.dumps(collect(args.model, args.runs),
                         indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "compare":
        a = collect(args.model, args.runs)
        b = collect(args.against, args.against_runs)
        print(json.dumps(compare(a, b), indent=2, ensure_ascii=False))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

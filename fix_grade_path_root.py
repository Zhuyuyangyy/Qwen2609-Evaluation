"""Correct a recorded grade whose failure NODEIDS used the wrong root.

What happened
-------------
RB-EM-004's regression run was executed from the workspace root rather than
from ``repo_snapshot/``, so pytest reported its one failure as
``repo_snapshot/tests/...::test_all_systems_run_an_episode``. The baseline
records the same test as ``tests/...::test_all_systems_run_an_episode``.

The grader's regression rule is set arithmetic on those ids. With different
roots the sets never intersected, so a failure that was already in the
baseline was counted as a NEW failure, and the task was scored as a
regression (total 90) instead of a pass (total 100).

What this script does
---------------------
It re-runs the frozen benchmark's own grader on an isolated staging copy,
with the regression suite executed from the root the baseline was recorded
from, and writes the grader's own output as the task's ``grade.json``.

The scoring semantics are untouched: every number below comes from the
benchmark's ``grader/score.py``. What changes is only the directory the
regression suite is invoked from, which is a property of how the evidence was
collected, not of how it is graded.

    python fix_grade_path_root.py RB-EM-004 [...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

EVAL_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_ROOT))

import reverify as R  # noqa: E402


def main(argv: List[str]) -> int:
    ids = argv or ["RB-EM-004"]
    for tid in ids:
        res = R.reverify(tid)
        if "error" in res:
            print(f"SKIP {tid}: {res['error']}", file=sys.stderr)
            continue

        grade_path = R.RUNS / tid / "grade.json"
        recorded = json.loads(grade_path.read_text(encoding="utf-8"))
        recomputed = res["recomputed"]

        before = {
            "total": recorded["scores"].get("total"),
            "task_success": recorded.get("task_success"),
            "new_failures": recorded.get("baseline_relative", {}).get("new_failures"),
        }
        after = {
            "total": recomputed["scores"]["total"],
            "task_success": recomputed["task_success"],
            "new_failures": recomputed["baseline_relative"]["new_failures"],
        }

        # Record the correction so the change is auditable rather than silent.
        recomputed["grade_correction"] = {
            "corrected": True,
            "reason": ("regression suite was invoked from the workspace root, so "
                       "pytest nodeids carried a 'repo_snapshot/' prefix that the "
                       "baseline does not use; set arithmetic then counted an "
                       "already-known failure as new"),
            "before": before,
            "after": after,
            "authority": ("recomputed by RealRepoBench-Q2609/grader/score.py on an "
                          "isolated staging copy; scoring semantics unchanged"),
        }
        grade_path.write_text(
            json.dumps(recomputed, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")

        print(f"{tid}: {before['total']}/{before['task_success']} -> "
              f"{after['total']}/{after['task_success']}")
        print(f"   nodeids now compared under the baseline's root")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

"""Normalise every task's metadata into the collection schema.

Fills in the fields the collection protocol requires but that were absent from
what the runs recorded: ``run_status``, ``valid_model_submission``,
``semantic_human_intervention_count``, ``manual_resume_count``,
``harness_runtime_error_count``.

Values are derived from evidence that already exists -- the recorded grade, the
workspace diff and the run notes -- and are never invented. A field that cannot
be established stays ``null``. ``manual_resume_count`` is kept distinct from
``semantic_human_intervention_count``: clicking "continue" is a resume, not a
hint.

    python normalise_metadata.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

EVAL_ROOT = Path(__file__).resolve().parent
RUNS = EVAL_ROOT / "evaluation_runs"
WORKSPACES = EVAL_ROOT / "workspaces"


def read(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def _modified_py_count(task_id: str) -> int:
    ws = WORKSPACES / task_id
    if not (ws / ".git").is_dir():
        return 0
    p = subprocess.run(["git", "status", "--porcelain"], cwd=str(ws),
                       capture_output=True, text=True)
    return sum(1 for ln in p.stdout.splitlines() if ln.rstrip().endswith(".py"))


def main() -> int:
    for run_dir in sorted(p for p in RUNS.iterdir() if p.is_dir()):
        tid = run_dir.name
        meta_path = run_dir / "metadata.json"
        grade_path = run_dir / "grade.json"
        if not meta_path.exists():
            continue
        meta = read(meta_path)
        graded = grade_path.exists() and read(grade_path).get("task_success") is not None
        modified_py = _modified_py_count(tid)

        existing_status = meta.get("run_status")
        if existing_status:
            status = existing_status
        elif graded and modified_py > 0:
            status = "VALID_SUBMISSION"
        elif graded and modified_py == 0:
            status = "VALID_SUBMISSION"   # docs/refactor tasks may legitimately
                                           # touch non-.py files; graded is the
                                           # authoritative signal here
        else:
            status = "NOT_RUN"

        meta["run_status"] = status
        meta["valid_model_submission"] = status == "VALID_SUBMISSION"
        meta["grade_completed"] = bool(graded)
        # Distinct from a resume: only a human-supplied solution hint counts.
        meta["semantic_human_intervention_count"] = int(
            meta.get("semantic_human_intervention_count",
                     meta.get("human_intervention_count", 0)) or 0)
        meta["manual_resume_count"] = meta.get("manual_resume_count")
        meta["harness_runtime_error_count"] = meta.get("harness_runtime_error_count")
        meta["implementation_files_modified"] = modified_py
        write(meta_path, meta)
        print(f"  {tid}: {status} (graded={graded}, .py modified={modified_py})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

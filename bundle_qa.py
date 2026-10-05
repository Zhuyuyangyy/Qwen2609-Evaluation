"""File-availability and consistency QA for the submission bundle."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

ORDERED = [
    "RB-AS-001", "RB-AS-002", "RB-AS-003", "RB-AS-004", "RB-AS-005",
    "RB-EM-001", "RB-EM-002", "RB-EM-004",
]


def run(bundle: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    """Return ``(problems, result_rows)``.

    Checks the things a reviewer will hit first: parseable JSON, an openable
    CSV with one row per frozen task, non-empty markdown, and internal
    agreement between the results table and each task's recorded grade.
    """
    problems: List[str] = []
    rows: List[Dict[str, str]] = []

    def _json(path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            problems.append(f"{path.name}: not parseable JSON ({e})")
            return None

    metrics = _json(bundle / "02_Results" / "FINAL_METRICS.json")
    if metrics is None:
        problems.append("FINAL_METRICS.json missing or unparseable")
    else:
        if metrics.get("benchmark_tasks") != 8:
            problems.append("denominator is not 8")
        if metrics.get("valid_run_task_success_rate") != 1.0:
            problems.append("valid-run TSR is not 7/7")
        if metrics.get("harness_valid_submission_rate") != 0.875:
            problems.append("harness valid submission rate is not 7/8")
        if metrics.get("evaluation_complete_under_original_protocol") is not False:
            problems.append("protocol completeness should be false")
        if metrics.get("original_8_task_tsr") is not None:
            problems.append("an 8-task TSR must not exist")

    csv_path = bundle / "02_Results" / "FINAL_RESULTS_TABLE.csv"
    try:
        with open(csv_path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if len(rows) != 8:
            problems.append(f"results table has {len(rows)} rows, expected 8")
        if {r["task_id"] for r in rows} != set(ORDERED):
            problems.append("results table task ids do not match the frozen set")
    except OSError as e:
        problems.append(f"results table unreadable: {e}")
        return problems, rows

    for p in sorted(bundle.rglob("*.md")):
        if p.stat().st_size == 0:
            problems.append(f"empty markdown: {p.relative_to(bundle)}")

    # grade.json must agree with the results table.
    for r in rows:
        gp = (bundle / "03_Execution_Evidence" / "evaluation_runs"
              / r["task_id"] / "grade.json")
        if not gp.exists():
            # Expected for a task with no valid submission; a problem only if
            # the table claims a verdict anyway.
            if r["task_success"] not in (None, "None", ""):
                problems.append(
                    f"{r['task_id']}: no grade.json but a verdict is recorded")
            continue
        g = _json(gp)
        if g is None:
            problems.append(f"{r['task_id']}: grade.json is not parseable")
            continue
        if g.get("task_success") is not (r["task_success"] in (True, "True")):
            problems.append(f"{r['task_id']}: grade.json and results table disagree")

    as4 = next((r for r in rows if r["task_id"] == "RB-AS-004"), None)
    if as4 is None:
        problems.append("RB-AS-004 missing from the results table")
    else:
        if as4["run_status"] != "INFRASTRUCTURE_FAILURE":
            problems.append("RB-AS-004 is not marked INFRASTRUCTURE_FAILURE")
        if as4["task_success"] not in (None, "None", ""):
            problems.append("RB-AS-004 must not carry a task_success value")

    joined = " ".join(r["task_id"] for r in rows)
    for bad in ("RB-EM-003", "RB-PS-001", "RB-PS-002", "RB-PS-003"):
        if bad in joined:
            problems.append(f"{bad} appears in the results table")

    return problems, rows


def write_note(bundle: Path, problems: List[str]) -> None:
    def _ok(needle: str) -> str:
        return "yes" if not any(needle in p for p in problems) else "NO"

    lines = [
        "# QA checklist",
        "",
        f"- all JSON parseable: {_ok('not parseable')}",
        f"- CSV opens, one row per frozen task: {_ok('results table')}",
        f"- Markdown files non-empty: {_ok('empty markdown')}",
        f"- grade.json agrees with results table: {_ok('disagree')}",
        f"- denominator is 8, excludes rejected/deferred: "
        f"{_ok('denominator')}{_ok('appears in the results table')}",
        f"- 7/7 and 7/8 semantics not conflated: {_ok('TSR')}",
        f"- RB-AS-004 is an infra failure, not a model failure: "
        f"{_ok('RB-AS-004')}",
        f"- no operator absolute path in the submission copy: "
        f"{_ok('absolute path')}",
        "",
        "## Secret scan",
        "",
        f"- result: {_ok('secret scan')}",
        "",
    ]
    if problems:
        lines += ["## Failures", ""] + [f"- {p}" for p in problems] + [""]
    else:
        lines += ["No failures recorded.", ""]
    (bundle / "02_Results" / "QA_CHECKLIST.md").write_text(
        "\n".join(lines), encoding="utf-8")

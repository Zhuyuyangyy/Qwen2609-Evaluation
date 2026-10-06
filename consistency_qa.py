"""Cross-file consistency QA for the submission bundle.

Checks that the same metric has the same VALUE and the same MEANING wherever it
appears. A single number quoted two ways is more damaging than a missing one,
because it survives review.

Files compared:

* ``02_Results/FINAL_METRICS.json``
* ``02_Results/EVALUATION_STATUS.json``
* ``02_Results/summary.json``
* ``05_Submission_Field_Materials/SUBMISSION_FIELD_FACTS.md``
* ``04_Harness_Reliability/HARNESS_RELIABILITY_FACTS.md``

Run:
    python consistency_qa.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

EVAL_ROOT = Path(__file__).resolve().parent
BUNDLE = EVAL_ROOT / "submission_bundle"

FINAL_METRICS = BUNDLE / "02_Results" / "FINAL_METRICS.json"
EVAL_STATUS = BUNDLE / "02_Results" / "EVALUATION_STATUS.json"
SUMMARY = BUNDLE / "02_Results" / "summary.json"
FIELD_FACTS = BUNDLE / "05_Submission_Field_Materials" / "SUBMISSION_FIELD_FACTS.md"
HARNESS_FACTS = BUNDLE / "04_Harness_Reliability" / "HARNESS_RELIABILITY_FACTS.md"

#: Every forbidden form of the zero-resume rate. A numeric rate over 8 is the
#: specific error this guards against.
FORBIDDEN_RATE_FORMS = [
    r"zero[-_ ]resume[^\n]{0,40}?=\s*0?\.\d+",
    r"zero[-_ ]resume[^\n]{0,40}?\d+\s*/\s*8",
]

#: Stated facts that must not appear anywhere.
FORBIDDEN_PHRASES = [
    "no manual resume and no recorded runtime error",
    "without any manual resume",
]

#: The exact task-type wording the submission standardises on.
TASK_TYPE_PHRASE = "4 declared task types across 7 tasks"


def _load(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def check() -> List[str]:
    problems: List[str] = []

    fm = _load(FINAL_METRICS)
    es = _load(EVAL_STATUS)
    sm = _load(SUMMARY)
    if fm is None:
        problems.append(f"missing/unparseable: {FINAL_METRICS.name}")
    if es is None:
        problems.append(f"missing/unparseable: {EVAL_STATUS.name}")
    if sm is None:
        problems.append(f"missing/unparseable: {SUMMARY.name}")
    if fm is None or es is None or sm is None:
        return problems

    facts = FIELD_FACTS.read_text(encoding="utf-8") if FIELD_FACTS.exists() else ""
    harness = (HARNESS_FACTS.read_text(encoding="utf-8")
               if HARNESS_FACTS.exists() else "")
    if not facts:
        problems.append(f"missing/empty: {FIELD_FACTS.name}")
    if not harness:
        problems.append(f"missing/empty: {HARNESS_FACTS.name}")

    # ── 1. core counts must match across all three JSON files ──
    shared_int = [
        ("benchmark_tasks", 8),
        ("infrastructure_failures", 1),
    ]
    for key, expected in shared_int:
        for label, doc in (("FINAL_METRICS", fm), ("EVALUATION_STATUS", es)):
            if doc.get(key) != expected:
                problems.append(f"{label}.{key}={doc.get(key)!r}, expected {expected}")

    # The two files name this one differently (valid_model_submissions vs
    # valid_model_runs), so accept either spelling rather than requiring a
    # duplicate key.
    for label, doc in (("FINAL_METRICS", fm), ("EVALUATION_STATUS", es)):
        got = doc.get("valid_model_submissions",
                      doc.get("valid_model_runs"))
        if got != 7:
            problems.append(f"{label} valid model submissions={got!r}, expected 7")

    # ── 2. model rate appears only in FINAL_METRICS, value 1.0 ──
    if fm.get("valid_run_task_success_rate") != 1.0:
        problems.append("FINAL_METRICS valid_run_TSR is not 7/7")

    # ── 3. harness rate must be identical in both files ──
    fm_harness = fm.get("harness_valid_submission_rate")
    es_harness = es.get("harness_valid_submission_rate")
    if fm_harness != es_harness:
        problems.append(
            f"harness_valid_submission_rate differs: FINAL_METRICS={fm_harness!r} "
            f"EVALUATION_STATUS={es_harness!r}")
    if fm_harness != 0.875:
        problems.append(f"harness rate is {fm_harness!r}, expected 0.875")

    # ── 4. no 8-task TSR may exist anywhere ──
    for label, doc in (("FINAL_METRICS", fm), ("EVALUATION_STATUS", es)):
        if doc.get("original_8_task_tsr") is not None:
            problems.append(f"{label} publishes an 8-task TSR")
        if doc.get("task_success_rate") not in (None,):
            problems.append(f"{label}.task_success_rate is not null")
    if sm.get("task_success_rate") is not None:
        problems.append("summary.json publishes a formal task_success_rate")
    if sm.get("evaluation_complete") is not False:
        problems.append("summary.json evaluation_complete is not false")

    # ── 5. zero-resume: null everywhere, with the same raw counts ──
    for label, doc in (("FINAL_METRICS", fm), ("EVALUATION_STATUS", es)):
        rate = doc.get("zero_resume_autonomous_completion_rate")
        if rate is not None:
            problems.append(
                f"{label}.zero_resume_autonomous_completion_rate={rate!r}; "
                f"must be null (unknown must not be scored as failure)")
        if doc.get("confirmed_zero_resume_tasks") != 1:
            problems.append(f"{label}.confirmed_zero_resume_tasks != 1")
        if doc.get("resume_count_known_tasks") != 1:
            problems.append(f"{label}.resume_count_known_tasks != 1")
        if doc.get("resume_count_unknown_tasks") != 7:
            problems.append(f"{label}.resume_count_unknown_tasks != 7")

    # ── 5b. machine-readable naming must not imply whole-set coverage ──
    # A bare "manual_resume_task_count" reads as "0 across all 8 tasks". The
    # fields are therefore named for their coverage, and the bare names are
    # rejected so the ambiguity cannot come back.
    for label, doc in (("FINAL_METRICS", fm), ("EVALUATION_STATUS", es)):
        for bare in ("manual_resume_task_count",
                     "harness_runtime_error_task_count",
                     "runtime_error_task_count",
                     "total_human_interventions"):
            if bare in doc:
                problems.append(
                    f"{label} still uses the ambiguous field name {bare!r}")
        for need in ("confirmed_manual_resume_task_count",
                     "manual_resume_count_coverage",
                     "manual_resume_count_status",
                     "confirmed_runtime_error_task_count",
                     "runtime_error_count_coverage",
                     "runtime_error_count_status"):
            if need not in doc:
                problems.append(f"{label} is missing {need!r}")
        if doc.get("manual_resume_count_status") != "PARTIAL_COVERAGE":
            problems.append(
                f"{label}.manual_resume_count_status should be PARTIAL_COVERAGE")
        if doc.get("runtime_error_count_status") != "PARTIAL_COVERAGE":
            problems.append(
                f"{label}.runtime_error_count_status should be PARTIAL_COVERAGE")
        if doc.get("manual_resume_count_coverage") != "1/8":
            problems.append(
                f"{label}.manual_resume_count_coverage="
                f"{doc.get('manual_resume_count_coverage')!r}, expected '1/8'")
        if doc.get("runtime_error_count_coverage") != "1/8":
            problems.append(
                f"{label}.runtime_error_count_coverage="
                f"{doc.get('runtime_error_count_coverage')!r}, expected '1/8'")

    if "total_human_interventions" in sm:
        problems.append(
            "summary.json still uses the ambiguous 'total_human_interventions'")
    for need in ("recorded_semantic_human_interventions",
                 "semantic_intervention_coverage"):
        if need not in sm:
            problems.append(f"summary.json is missing {need!r}")

    # ── 6. duration: no representative median while coverage is 2/8 ──
    if sm.get("median_duration_seconds") is not None:
        problems.append(
            f"summary.json median_duration_seconds="
            f"{sm['median_duration_seconds']!r}; must be null at 2/8 coverage")
    if sm.get("duration_coverage") != "2/8":
        problems.append(f"summary.json duration_coverage={sm.get('duration_coverage')!r}")
    cov = fm.get("duration_coverage", {})
    if cov.get("tasks_with_duration") != 2:
        problems.append("FINAL_METRICS duration coverage is not 2")
    if cov.get("median_duration_seconds") is not None:
        problems.append("FINAL_METRICS publishes a duration median")

    # ── 7. prose must not state a forbidden simplification ──
    for name, text in (("SUBMISSION_FIELD_FACTS", facts),
                       ("HARNESS_RELIABILITY_FACTS", harness)):
        low = text.lower()
        for phrase in FORBIDDEN_PHRASES:
            if phrase in low:
                problems.append(f"{name} still states {phrase!r}")
        for pat in FORBIDDEN_RATE_FORMS:
            if re.search(pat, low):
                problems.append(f"{name} states a numeric zero-resume rate")

    # ── 8. prose must carry the required task-type wording ──
    for name, text in (("SUBMISSION_FIELD_FACTS", facts),
                       ("HARNESS_RELIABILITY_FACTS", harness)):
        if name == "SUBMISSION_FIELD_FACTS" and TASK_TYPE_PHRASE not in text:
            problems.append(f"{name} lacks the standardised task-type wording")

    # ── 8b. prose must not extrapolate a partial-coverage zero to the whole set
    # The JSON fields are correct; the risk is a sentence that reads the same
    # zero as "confirmed across all 8 tasks".
    import re as _re
    full_coverage_claims = [
        r"no task[^.\n]{0,40}recorded[^.\n]{0,30}semantic",
        r"none[^.\n]{0,20}recorded anywhere",
        r"zero[- ]resume[^.\n]{0,40}across[^.\n]{0,20}(benchmark|8 tasks)",
        r"all (8|eight) tasks[^.\n]{0,40}(0|zero|no manual resume)",
        r"manual resume[^.\n]{0,20}(across|for) (all|every) (8|eight|task)",
    ]
    for name, text in (("SUBMISSION_FIELD_FACTS", facts),
                       ("HARNESS_RELIABILITY_FACTS", harness)):
        low = text.lower()
        for pat in full_coverage_claims:
            if _re.search(pat, low):
                problems.append(
                    f"{name} extrapolates a partial-coverage zero to the whole "
                    f"benchmark (matched /{pat}/)")

    # A zero-resume rate may not be restated as a number.
    if "12.5" in facts or "87.5" in facts:
        if "zero-resume" in facts.lower():
            problems.append("SUBMISSION_FIELD_FACTS quotes a numeric zero-resume rate")

    # ── 9. evidence paths that are cited must exist in the bundle ──
    cited = set(re.findall(r"0\d_[A-Za-z_]+/[A-Za-z0-9_.\-]+", facts + harness))
    for rel in sorted(cited):
        if rel.endswith(("/", "*")):
            continue
        if not (BUNDLE / rel).exists() and not (BUNDLE / rel.rstrip("/")).is_dir():
            problems.append(f"cited path does not exist in the bundle: {rel}")

    # ── 10. no operator absolute path may remain ──
    sys.path.insert(0, str(EVAL_ROOT))
    from relativise import find_residual
    for p in sorted(BUNDLE.rglob("*")):
        if not p.is_file() or p.suffix.lower() in {".pyc", ".db", ".png", ".gz"}:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        residual = find_residual(text)
        if residual:
            problems.append(
                f"absolute path in {p.relative_to(BUNDLE)}: {residual[:1]}")

    # ── 11. RB-AS-004 stays an infra failure, never a model failure ──
    for row in _rows(sm):
        if row.get("task_id") == "RB-AS-004":
            if row.get("run_status") != "INFRASTRUCTURE_FAILURE":
                problems.append("RB-AS-004 is not INFRASTRUCTURE_FAILURE")
            if row.get("task_success") not in (None, "", "None"):
                problems.append("RB-AS-004 carries a task_success value")

    return problems


def _rows(summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Rows from the CSV companion, keyed to the summary."""
    import csv
    csv_path = BUNDLE / "02_Results" / "FINAL_RESULTS_TABLE.csv"
    if not csv_path.exists():
        return []
    with open(csv_path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> int:
    problems = check()
    if problems:
        print(f"CONSISTENCY FAILURES: {len(problems)}")
        for p in problems:
            print("  -", p)
        return 1
    print("CONSISTENCY OK: FINAL_METRICS / EVALUATION_STATUS / summary / "
          "SUBMSSION_FIELD_FACTS / HARNESS_RELIABILITY_FACTS agree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

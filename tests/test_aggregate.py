"""Synthetic-fixture tests for aggregate.py.

Covers the six cases that must not silently pass:

  A  8/8 graded                     -> evaluation_complete = true
  B  5/8 graded                     -> incomplete, formal rate null, provisional given
  C  a non-frozen task appears      -> hard reject
  D  duplicate task_id              -> hard reject
  E  task_success disagrees         -> hard reject
  F  pre-existing baseline failure  -> must not be re-interpreted by the aggregate

The fixtures never touch the frozen benchmark: everything is written into a
tmp directory and read back.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

EVAL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EVAL_ROOT))

import aggregate as agg  # noqa: E402

FROZEN = sorted(agg.frozen_set_from_harness())


@pytest.fixture()
def bench(tmp_path, monkeypatch):
    """A manifest on disk declaring the real frozen set.

    The real ``harness/manifest.py`` is copied in so ``FROZEN_SET`` can be
    read from it -- a synthetic declaration would make the cross-check test
    vacuous.
    """
    manifest = {
        "benchmark": "RealRepoBench-Q2609",
        "version": "0.1",
        "frozen": True,
        "tasks": [
            {"task_id": t, "repository": "AgentShield_V3",
             "task_type": "hidden_only_bug", "capabilities": ["x"],
             "difficulty": "medium", "ready": True}
            for t in FROZEN
        ] + [
            {"task_id": "RB-EM-003",
             "repository": "emotion-like-functional-modulation-main",
             "task_type": "docs_consistency", "capabilities": [],
             "difficulty": "easy", "ready": False}
        ],
    }
    b = tmp_path / "bench"
    (b / "harness").mkdir(parents=True)
    (b / "benchmark_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8")
    src = agg.BENCH_ROOT / "harness" / "manifest.py"
    (b / "harness" / "manifest.py").write_bytes(src.read_bytes())
    monkeypatch.setattr(agg, "BENCH_ROOT", b)
    return b


def _manifest(bench):
    return json.loads((bench / "benchmark_manifest.json").read_text(encoding="utf-8"))


def _rewrite_manifest(bench, manifest):
    (bench / "benchmark_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8")


def _grade(task_id, *, success=True, total=None, public=None, hidden=None,
           target_fix=True, regression_pass=True, constraint=10):
    """Build a grade.json shaped exactly like the grader's ``Score.to_dict()``.

    The boolean ``public_tests_pass`` / ``hidden_tests_pass`` fields are NOT
    present, because the grader does not emit them. A fixture that included
    them would make the aggregate tests pass against a schema no real run can
    produce -- which is precisely the bug the smoke run caught.
    """
    if total is None:
        total = 100 if success else 40
    functional = 60 if success else 0
    if public is False or hidden is False:
        functional = 0
    hidden_score = 20 if (hidden if hidden is not None else success) else 0
    if hidden is False:
        hidden_score = 0
    return {
        "task_id": task_id,
        "task_success": success,
        "scores": {
            "functional_correctness": functional,
            "hidden_tests": hidden_score,
            "constraint_compliance": constraint,
            "no_regression": 10 if regression_pass else 0,
            "total": total,
        },
        "baseline_relative": {
            "target_fix_pass": target_fix,
            "regression_pass": regression_pass,
            "new_failures": [],
            "surviving_target_failures": [],
        },
    }


def _write_runs(root, task_ids, *, mutate=None):
    root.mkdir(parents=True, exist_ok=True)
    for tid in task_ids:
        d = root / tid
        d.mkdir()
        grade = _grade(tid) if mutate is None else mutate(tid)
        (d / "grade.json").write_text(json.dumps(grade), encoding="utf-8")
        (d / "metadata.json").write_text(json.dumps(
            {"duration_seconds": 120.0, "human_intervention_count": 0,
             "execution_completed": True, "grade_completed": True,
             "files_modified_count": 1}), encoding="utf-8")
    return root


# -- Case A: complete ------------------------------------------------------
def test_case_a_eight_of_eight_is_complete(tmp_path, bench):
    runs = _write_runs(tmp_path / "runs", FROZEN)
    result = agg.aggregate(runs, FROZEN, bench_root=bench)
    s = result["summary"]
    assert s["graded_tasks"] == 8
    assert s["frozen_tasks"] == 8
    assert s["evaluation_complete"] is True
    assert s["task_success_rate"] == 1.0
    assert "provisional_task_success_rate" not in s
    assert s["missing_tasks"] == []


# -- Case B: partial -------------------------------------------------------
def test_case_b_five_of_eight_is_not_published_as_final(tmp_path, bench):
    runs = _write_runs(tmp_path / "runs", FROZEN[:5])
    result = agg.aggregate(runs, FROZEN, bench_root=bench)
    s = result["summary"]
    assert s["graded_tasks"] == 5
    assert s["evaluation_complete"] is False
    assert s["task_success_rate"] is None, (
        "a partial run must never be reported as the formal rate"
    )
    assert s["provisional_task_success_rate"] == 1.0
    assert sorted(s["missing_tasks"]) == sorted(FROZEN[5:])


def test_case_b_missing_rows_are_neither_success_nor_failure(tmp_path, bench):
    runs = _write_runs(tmp_path / "runs", FROZEN[:5])
    result = agg.aggregate(runs, FROZEN, bench_root=bench)
    missing = [r for r in result["rows"] if r["failure_category"] == "MISSING"]
    assert len(missing) == 3
    for row in missing:
        assert row["task_success"] is None, "missing must not be scored a success"
        assert row["grade_completed"] is False
    assert all(f["task_id"] in FROZEN[:5] for f in result["failures"])


# -- Case C: a non-frozen task enters -------------------------------------
def test_case_c_non_frozen_task_is_rejected(tmp_path, bench):
    runs = _write_runs(tmp_path / "runs", FROZEN[:4])
    (runs / "RB-EM-003").mkdir()
    (runs / "RB-EM-003" / "grade.json").write_text(
        json.dumps(_grade("RB-EM-003")), encoding="utf-8")
    with pytest.raises(agg.AggregationError) as e:
        agg.aggregate(runs, FROZEN, bench_root=bench)
    assert "RB-EM-003" in str(e.value)


def test_case_c_deferred_phyto_task_is_rejected(tmp_path, bench):
    runs = _write_runs(tmp_path / "runs", FROZEN[:4])
    (runs / "RB-PS-001").mkdir()
    (runs / "RB-PS-001" / "grade.json").write_text(
        json.dumps(_grade("RB-PS-001")), encoding="utf-8")
    with pytest.raises(agg.AggregationError):
        agg.aggregate(runs, FROZEN, bench_root=bench)


# -- Case D: duplicate task_id --------------------------------------------
def test_case_d_duplicate_task_id_is_rejected(tmp_path, bench):
    runs = _write_runs(tmp_path / "runs", FROZEN[:4])
    (runs / "copy").mkdir()
    (runs / "copy" / "grade.json").write_text(
        json.dumps(_grade(FROZEN[0])), encoding="utf-8")
    with pytest.raises(agg.AggregationError) as e:
        agg.aggregate(runs, FROZEN, bench_root=bench)
    assert "duplicate" in str(e.value).lower()


# -- Case E: task_success disagrees with the components -------------------
def test_case_e_success_verdict_must_agree_with_grader(tmp_path, bench):
    def broken(tid):
        g = _grade(tid, success=False)
        g["task_success"] = True
        return g
    runs = _write_runs(tmp_path / "runs", FROZEN[:4], mutate=broken)
    with pytest.raises(agg.AggregationError) as e:
        agg.aggregate(runs, FROZEN, bench_root=bench)
    assert "task_success" in str(e.value)


def test_case_e_impossible_total_is_rejected(tmp_path, bench):
    def broken(tid):
        g = _grade(tid)
        g["scores"]["total"] = 900
        return g
    runs = _write_runs(tmp_path / "runs", FROZEN[:4], mutate=broken)
    with pytest.raises(agg.AggregationError) as e:
        agg.aggregate(runs, FROZEN, bench_root=bench)
    assert "0..100" in str(e.value)


def test_case_e_negative_duration_is_rejected(tmp_path, bench):
    runs = _write_runs(tmp_path / "runs", FROZEN[:4])
    (runs / FROZEN[0] / "metadata.json").write_text(json.dumps(
        {"duration_seconds": -5, "human_intervention_count": 0}),
        encoding="utf-8")
    with pytest.raises(agg.AggregationError) as e:
        agg.aggregate(runs, FROZEN, bench_root=bench)
    assert "duration_seconds" in str(e.value)


def test_case_e_negative_interventions_is_rejected(tmp_path, bench):
    runs = _write_runs(tmp_path / "runs", FROZEN[:4])
    (runs / FROZEN[0] / "metadata.json").write_text(json.dumps(
        {"duration_seconds": 10, "human_intervention_count": -1}),
        encoding="utf-8")
    with pytest.raises(agg.AggregationError) as e:
        agg.aggregate(runs, FROZEN, bench_root=bench)
    assert "human_intervention_count" in str(e.value)


# -- Case F: pre-existing baseline failure is not re-judged ---------------
def test_case_f_preexisting_failure_is_not_a_regression(tmp_path, bench):
    """The grader already decided this; the aggregate must pass it through.

    RegressionPass=true alongside a recorded upstream failure is a legitimate
    outcome for a repository that ships a broken test.
    """

    def run(tid):
        g = _grade(tid)
        g["baseline_relative"]["regression_pass"] = True
        g["baseline_relative"]["known_preexisting_failures"] = [
            "tests/test_x.py::test_already_broken"
        ]
        return g

    runs = _write_runs(tmp_path / "runs", FROZEN, mutate=run)
    result = agg.aggregate(runs, FROZEN, bench_root=bench)
    s = result["summary"]
    assert s["regression_pass_rate"] == 1.0
    assert s["task_success_rate"] == 1.0
    assert result["failures"] == []


def test_case_f_real_regression_is_classified_as_such(tmp_path, bench):
    def run(tid):
        g = _grade(tid, success=False, public=True, hidden=True)
        g["baseline_relative"]["regression_pass"] = False
        g["baseline_relative"]["new_failures"] = ["tests/test_y.py::test_new"]
        return g

    runs = _write_runs(tmp_path / "runs", FROZEN, mutate=run)
    result = agg.aggregate(runs, FROZEN, bench_root=bench)
    assert result["summary"]["task_success_rate"] == 0.0
    assert {f["failure_category"] for f in result["failures"]} == {"REGRESSION"}


# -- denominator guards ---------------------------------------------------
def test_denominator_must_be_exactly_eight(bench):
    manifest = _manifest(bench)
    manifest["tasks"] = [t for t in manifest["tasks"] if t["task_id"] != FROZEN[-1]]
    _rewrite_manifest(bench, manifest)
    with pytest.raises(agg.AggregationError) as e:
        agg.load_frozen_set(bench)
    # The manifest now disagrees with the benchmark's own frozen-set decl.
    assert "disagrees" in str(e.value)


def test_unfrozen_manifest_is_refused(bench):
    manifest = _manifest(bench)
    manifest["frozen"] = False
    _rewrite_manifest(bench, manifest)
    with pytest.raises(agg.AggregationError) as e:
        agg.load_frozen_set(bench)
    assert "frozen" in str(e.value)


def test_count_guard_is_independent_of_the_agreement_guard(bench):
    """A manifest with 7 ready tasks is refused on the count, not by accident."""
    manifest = _manifest(bench)
    manifest["tasks"] = [t for t in manifest["tasks"]
                         if t["task_id"] != FROZEN[-1]]
    # Present the manifest as agreeing with a 7-task declaration, so the only
    # remaining reason to refuse is the count.
    (bench / "harness" / "manifest.py").write_text(
        'FROZEN_SET = {\n'
        + "".join(f'    "{t}",\n' for t in FROZEN[:-1])
        + "}\n",
        encoding="utf-8")
    _rewrite_manifest(bench, manifest)
    with pytest.raises(agg.AggregationError) as e:
        agg.load_frozen_set(bench)
    assert "expected 8" in str(e.value)


def test_manifest_and_harness_frozen_sets_agree(bench):
    """The manifest must not disagree with the benchmark's own declaration."""
    assert set(agg.load_frozen_set(bench)) == agg.frozen_set_from_harness()


def test_no_frozen_task_is_rejected_or_deferred():
    """The frozen set must not contain a task the benchmark excluded."""
    assert not (set(FROZEN) & agg.REJECTED_OR_DEFERRED)
    assert len(FROZEN) == 8


# -- taxonomy -------------------------------------------------------------
def test_failure_categories_are_all_in_the_controlled_taxonomy():
    assert "UNKNOWN" in agg.FAILURE_TAXONOMY
    assert len(set(agg.FAILURE_TAXONOMY)) == len(agg.FAILURE_TAXONOMY)
    assert "MISSING" not in agg.FAILURE_TAXONOMY, (
        "MISSING is a state, not a failure category"
    )


def test_constraint_violation_classification():
    g = _grade("RB-AS-001", success=False)
    g["scores"]["constraint_compliance"] = 0
    rec = agg.GradeRecord("RB-AS-001", g, {}, Path("."))
    cat, summary = agg.classify_failure(rec)
    assert cat == "CONSTRAINT_VIOLATION"
    assert "frozen" in summary


def test_localization_classification():
    g = _grade("RB-AS-001", success=False, public=False, hidden=False)
    rec = agg.GradeRecord("RB-AS-001", g, {}, Path("."))
    cat, _ = agg.classify_failure(rec)
    assert cat == "LOCALIZATION_FAILURE"


def test_timeout_classification():
    g = _grade("RB-AS-001", success=False)
    rec = agg.GradeRecord("RB-AS-001", g, {"timed_out": True}, Path("."))
    cat, _ = agg.classify_failure(rec)
    assert cat == "TIMEOUT"


def test_incomplete_fix_classification():
    g = _grade("RB-EM-004", success=False, public=True, hidden=False)
    g["baseline_relative"]["target_fix_pass"] = False
    g["baseline_relative"]["surviving_target_failures"] = [
        "tests/test_x.py::test_target"
    ]
    rec = agg.GradeRecord("RB-EM-004", g, {}, Path("."))
    cat, summary = agg.classify_failure(rec)
    assert cat == "INCOMPLETE_FIX"
    assert "test_target" in summary


# -- output shape ---------------------------------------------------------
def test_written_outputs_have_the_required_files(tmp_path, bench):
    runs = _write_runs(tmp_path / "runs", FROZEN)
    out = tmp_path / "out"
    result = agg.aggregate(runs, FROZEN, bench_root=bench)
    agg.write_outputs(result, out)

    for name in ("results.csv", "summary.json", "failure_cases.jsonl",
                 "AGGREGATION_REPORT.md"):
        assert (out / name).exists(), name

    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    for key in ("benchmark", "version", "frozen_tasks", "evaluated_tasks",
                "graded_tasks", "successful_tasks", "task_success_rate",
                "public_test_pass_rate", "hidden_test_pass_rate",
                "target_fix_rate", "regression_pass_rate",
                "constraint_violation_rate", "mean_total_score",
                "median_duration_seconds", "total_human_interventions",
                "by_repository", "by_task_type"):
        assert key in summary, key

    import csv
    with open(out / "results.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 8
    assert {r["task_id"] for r in rows} == set(FROZEN)


def test_failure_cases_only_contains_failures(tmp_path, bench):
    def run(tid):
        return _grade(tid, success=(tid != FROZEN[0]))

    runs = _write_runs(tmp_path / "runs", FROZEN, mutate=run)
    out = tmp_path / "out"
    result = agg.aggregate(runs, FROZEN, bench_root=bench)
    agg.write_outputs(result, out)

    lines = [json.loads(l) for l in
             (out / "failure_cases.jsonl").read_text(encoding="utf-8").splitlines()
             if l.strip()]
    assert [f["task_id"] for f in lines] == [FROZEN[0]]
    assert lines[0]["failure_category"] in agg.FAILURE_TAXONOMY

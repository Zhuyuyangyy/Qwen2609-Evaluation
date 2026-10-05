"""Build a small smoke run from the REAL grader's output.

The purpose is to exercise aggregate.py against genuine grader verdicts rather
than only against synthetic fixtures, so the two components are shown to agree.

A module loaded by path also has to be registered in ``sys.modules`` for
``@dataclass`` to resolve its own annotation strings; without that, importing
score.py raises inside ``dataclasses``.

    python make_smoke_runs.py [--runs DIR] [--tasks N]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path

EVAL_ROOT = Path(__file__).resolve().parent
BENCH = EVAL_ROOT.parent / "RealRepoBench-Q2609"
sys.path.insert(0, str(EVAL_ROOT))

import aggregate as agg  # noqa: E402


def load_grader():
    spec = importlib.util.spec_from_file_location(
        "bench_score", BENCH / "grader" / "score.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["bench_score"] = module   # dataclass needs this
    spec.loader.exec_module(module)
    return module


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, default=EVAL_ROOT / "evaluation_runs")
    ap.add_argument("--tasks", type=int, default=5,
                    help="how many of the frozen tasks to emit (default 5, i.e. partial)")
    args = ap.parse_args(argv)

    score = load_grader()
    frozen = sorted(agg.frozen_set_from_harness())

    if args.runs.exists():
        shutil.rmtree(args.runs)
    args.runs.mkdir(parents=True)

    ok = score.TestRun(exit_code=0, passed=5, failed=0, failed_test_ids=[])
    bad_hidden = score.TestRun(exit_code=1, passed=2, failed=3,
                               failed_test_ids=["tests/test_a.py::test_x",
                                                "tests/test_b.py::test_y"])
    bad_regression = score.TestRun(exit_code=1, passed=3, failed=2,
                                   failed_test_ids=["tests/test_c.py::test_new"])

    emitted = []
    for index, tid in enumerate(frozen[:args.tasks]):
        if index == 3:
            # a genuine grader-produced failure: hidden checks red
            s = score.grade_task(tid, public_tests=ok, hidden_tests=bad_hidden,
                                 regression_tests=ok, violations=[],
                                 hidden_cases_total=3,
                                 baseline_failures=[], target_failures=[])
        elif index == 4:
            # a genuine grader-produced failure: a new regression
            s = score.grade_task(tid, public_tests=ok, hidden_tests=ok,
                                 regression_tests=bad_regression, violations=[],
                                 hidden_cases_total=3,
                                 baseline_failures=[], target_failures=[])
        else:
            s = score.grade_task(tid, public_tests=ok, hidden_tests=ok,
                                 regression_tests=ok, violations=[],
                                 hidden_cases_total=3,
                                 baseline_failures=[], target_failures=[])

        run_dir = args.runs / tid
        run_dir.mkdir()
        (run_dir / "grade.json").write_text(
            json.dumps(s.to_dict(), ensure_ascii=False) + "\n", encoding="utf-8")
        (run_dir / "metadata.json").write_text(json.dumps({
            "duration_seconds": 300.0 + index * 30,
            "human_intervention_count": index % 2,
            "execution_completed": True,
            "grade_completed": True,
            "files_modified_count": 2 + index,
        }, ensure_ascii=False) + "\n", encoding="utf-8")
        emitted.append((tid, s.task_success))

    for tid, success in emitted:
        print(f"  {tid}: grader task_success={success}")
    print(f"wrote {len(emitted)} graded run(s) to {args.runs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

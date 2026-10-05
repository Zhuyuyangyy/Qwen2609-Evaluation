"""Re-verify a graded run independently, outside the agent's workspace.

The operator's job includes checking that a recorded grade is real. This
re-runs the frozen benchmark's own grader against a STAGING COPY of the
agent's submitted tree, so:

* the agent's workspace is never modified,
* hidden tests and the grader never enter the workspace,
* the recomputed verdict can be compared with the recorded grade.json.

A disagreement is reported, not silently reconciled: if the recorded grade
and the recomputed one differ, the recorded grade is the one under suspicion.

    python reverify.py RB-AS-005 [RB-AS-001 ...]
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

EVAL_ROOT = Path(__file__).resolve().parent
BENCH = EVAL_ROOT.parent / "RealRepoBench-Q2609"
WORKSPACES = EVAL_ROOT / "workspaces"
RUNS = EVAL_ROOT / "evaluation_runs"

TASKS = [
    "RB-AS-001", "RB-AS-002", "RB-AS-003", "RB-AS-004", "RB-AS-005",
    "RB-EM-001", "RB-EM-002", "RB-EM-004",
]


def load_grader():
    spec = importlib.util.spec_from_file_location(
        "bench_score_reverify", BENCH / "grader" / "score.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["bench_score_reverify"] = module
    spec.loader.exec_module(module)
    return module


def _read_text_any(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _run_tests(cwd: Path, target: str, timeout: int = 1800) -> Dict[str, Any]:
    """Run pytest in an isolated directory and parse its summary line."""
    env = dict(**os.environ, PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", target],
        cwd=str(cwd), capture_output=True, text=True, timeout=timeout, env=env,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    import re
    def _num(pat):
        m = re.search(pat, out)
        return int(m.group(1)) if m else 0
    failed_names = [
        ln.split(" ", 1)[1].strip()
        for ln in out.splitlines()
        if ln.startswith("FAILED ") or ln.startswith("ERROR ")
    ]
    return {
        "exit_code": proc.returncode,
        "passed": _num(r"(\d+) passed"),
        "failed": _num(r"(\d+) failed"),
        "errors": _num(r"(\d+) error"),
        "skipped": _num(r"(\d+) skipped"),
        "failed_test_ids": failed_names,
        "raw_tail": out[-1500:],
    }


def reverify(task_id: str, keep: bool = False) -> Dict[str, Any]:
    """Grade one submitted workspace on an isolated staging copy."""
    ws = WORKSPACES / task_id
    run_dir = RUNS / task_id
    recorded_path = run_dir / "grade.json"

    result: Dict[str, Any] = {"task_id": task_id}
    if not ws.is_dir():
        result["error"] = f"workspace missing: {ws}"
        return result
    if not recorded_path.exists():
        result["error"] = "no recorded grade.json to compare against"
        return result
    recorded = json.loads(recorded_path.read_text(encoding="utf-8"))
    if recorded.get("task_success") is None:
        result["error"] = ("recorded grade is a placeholder (task_success null); "
                           "nothing to re-verify")
        return result

    score = load_grader()
    staging = Path(tempfile.mkdtemp(prefix=f"reverify-{task_id}-"))
    try:
        work = staging / "work"
        shutil.copytree(ws, work)
        # Drop caches so they do not affect the run or the checksums.
        for junk in ("__pycache__", ".pytest_cache"):
            for p in work.rglob(junk):
                shutil.rmtree(p, ignore_errors=True)

        suite_root = work if (work / "repo_snapshot").is_dir() is False \
            else work / "repo_snapshot"

        # Private grading: run the EMBARGOED checks from the frozen benchmark
        # against the staging copy. They are never copied into the workspace.
        hidden_src = BENCH / "tasks" / task_id / "hidden_tests"
        public_src = BENCH / "tasks" / task_id / "public_tests"
        shutil.copytree(hidden_src, work / "hidden_tests")
        shutil.copytree(public_src, work / "public_tests", dirs_exist_ok=True)

        public = _run_tests(work, "public_tests")
        hidden = _run_tests(work, "hidden_tests")
        regression = _run_tests(suite_root, ".", timeout=2400)

        # Frozen-file check against the task's own checksum list.
        checksums = BENCH / "tasks" / task_id / "checksums.sha256"
        violations: List[Dict[str, str]] = []
        if checksums.exists():
            from hashlib import sha256
            for line in checksums.read_text(encoding="utf-8").splitlines():
                if not line.strip() or line.startswith("#"):
                    continue
                digest, _size, rel = line.split(None, 2)
                p = suite_root / rel.strip()
                if not p.exists():
                    violations.append({"path": rel.strip(),
                                       "sha256_snapshot": digest,
                                       "sha256_submitted": "",
                                       "reason": "deleted"})
                    continue
                actual = sha256(p.read_bytes()).hexdigest()
                if actual != digest:
                    violations.append({"path": rel.strip(),
                                       "sha256_snapshot": digest,
                                       "sha256_submitted": actual,
                                       "reason": "modified"})

        baseline, target_failures = _baseline_and_target(task_id)
        degraded = TestRunWrap(hidden, public, regression)
        s = score.grade_task(
            task_id,
            public_tests=score.TestRun(**public_run_kwargs(public)),
            hidden_tests=score.TestRun(**public_run_kwargs(hidden)),
            regression_tests=score.TestRun(**public_run_kwargs(regression)),
            violations=[score.FrozenFileViolation(**v) for v in violations],
            hidden_cases_total=_hidden_total(task_id),
            baseline_failures=baseline,
            target_failures=target_failures,
        )
        recomputed = s.to_dict()

        result["recomputed"] = recomputed
        result["recorded"] = recorded
        result["agrees"] = (
            recomputed["task_success"] == recorded["task_success"]
            and recomputed["scores"]["total"] == recorded["scores"]["total"]
        )
        result["detail"] = {
            "public": public, "hidden": hidden, "regression": regression,
            "violations": violations,
        }
    finally:
        if not keep:
            shutil.rmtree(staging, ignore_errors=True)
    return result


class TestRunWrap:
    def __init__(self, *runs):
        self.runs = runs


def public_run_kwargs(r: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "exit_code": r["exit_code"],
        "passed": r["passed"],
        "failed": r["failed"],
        "errors": r["errors"],
        "skipped": r["skipped"],
        "failed_test_ids": r["failed_test_ids"],
        "raw_tail": r["raw_tail"],
    }


def _baseline_and_target(task_id: str):
    p = BENCH / "tasks" / task_id / "baseline_failures.json"
    if not p.exists():
        return [], []
    d = json.loads(p.read_text(encoding="utf-8"))
    return (list(d.get("known_preexisting_failures", [])),
            list(d.get("target_failures", [])))


def _hidden_total(task_id: str) -> int:
    for line in (BENCH / "tasks.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            if r["task_id"] == task_id:
                return int(r.get("hidden_case_count", 0) or 0)
    return 0


def main(argv: List[str]) -> int:
    ids = argv or TASKS
    rows = []
    for tid in ids:
        res = reverify(tid)
        rows.append(res)
        if "error" in res:
            print(f"  SKIP {tid}: {res['error']}")
            continue
        mark = "AGREES " if res["agrees"] else "DIFFERS"
        print(f"  {mark} {tid}: recorded total="
              f"{res['recorded']['scores'].get('total')} "
              f"success={res['recorded'].get('task_success')} | "
              f"recomputed total={res['recomputed']['scores']['total']} "
              f"success={res['recomputed']['task_success']}")
        if not res["agrees"]:
            d = res["detail"]
            print(f"        public={d['public']['passed']}P/{d['public']['failed']}F "
                  f"hidden={d['hidden']['passed']}P/{d['hidden']['failed']}F "
                  f"regression={d['regression']['passed']}P/{d['regression']['failed']}F "
                  f"violations={len(d['violations'])}")

    out = EVAL_ROOT / "REVERIFICATION.json"
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(f"\nwritten to {out.name}")
    differing = [r["task_id"] for r in rows if not r.get("agrees") and "error" not in r]
    if differing:
        print(f"DIFFERS: {', '.join(differing)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

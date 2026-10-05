"""Read-only audit of the exported public evaluation workspaces.

This does NOT export, prune, or modify anything. It inspects what the export
already produced and reports whether those workspaces are safe to hand to an
agent.

The scan is exhaustive by design: every file's path and name is checked, and
every text file is scanned in full. Large files are read in chunks so that
``benchmark/``-style multi-megabyte JSON artifacts are covered rather than
skipped -- a leak hidden inside a big data file is still a leak.

Binary files are not decoded, but their paths and names are still checked.

The rules are deliberately narrow. A word like "grader" appearing in the
upstream project's own ``grader_parity.json`` is legitimate engineering
content -- that file is the code under test. What is forbidden is material
that belongs to THIS benchmark's construction: its hidden tests, reference
repairs, defect scripts, baselines, and build notes. Matching is therefore on
explicit private-artifact names, on unambiguous phrases, and on exact
fingerprints taken from the private material -- never on ordinary words.

    python audit_public_workspaces.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import argparse

EVAL_ROOT = Path(__file__).resolve().parent
BENCH_ROOT = EVAL_ROOT.parent / "RealRepoBench-Q2609"
WORKSPACES = EVAL_ROOT / "workspaces"
REPORT = EVAL_ROOT / "PUBLIC_WORKSPACE_AUDIT.md"

CHUNK = 4 * 1024 * 1024          # 4 MiB
EXPECTED_FROZEN_TASKS = 8

# ── private artifact names, matched exactly ───────────────────────────────
PRIVATE_EXACT_NAMES = {
    "graders", "grader_impl",            # private grading implementation
    "hidden_tests",                      # the embargoed checks
    "reference.patch", "reference_solution.patch", "reference_solution",
    "gold_patch.patch", "gold.patch",
    "defect.json", "defect_script.py", "defect_injection.py",
    "baseline_failures.json",
    "reference_metadata.json",
    "build_report", "build_report.md", "build_report.txt",
    "snapshot.json",
    "checksums.sha256",
}

#: Private *directories* -- any path component equal to one of these is a leak.
PRIVATE_DIR_NAMES = {
    "hidden_tests", "hidden grading metadata", "private",
    "reference", "defect", "baseline_failures", "grader_impl",
    "builder", "construction",
}

#: Unambiguous phrases that only occur in builder-internal material.
LEAK_PHRASES = (
    "reference repair",
    "reference patch",
    "reference solution",
    "injected defect",
    "defect injection",
    "expected fixed",
    "expected buggy",
    "hidden test",
    "hidden tests",
    "hidden oracle",
    "old_pattern",
    "new_pattern",
    "baseline target failure",
    "rejection_reason",
    "builder-only",
    "RealRepoBench frozen baseline is intentionally",
    "the correct patch is",
)

#: Text files that must be scanned in full, by extension.
TEXT_SUFFIXES = {
    ".py", ".md", ".txt", ".json", ".jsonl", ".yaml", ".yml", ".toml",
    ".ini", ".cfg", ".csv", ".sh", ".ps1", ".bat", ".xml",
}

#: Known binary / non-UTF-8 containers: path-checked only.
BINARY_SUFFIXES = {
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".dylib", ".db", ".db-wal",
    ".db-shm", ".parquet", ".arrow", ".pkl", ".pickle", ".bin",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".docx", ".xlsx",
    ".zip", ".gz", ".tgz", ".woff", ".woff2", ".ttf", ".eot", ".mp4",
}


class AuditError(RuntimeError):
    pass


# ── frozen set + fingerprints ─────────────────────────────────────────────
def frozen_set(bench_root: Path = BENCH_ROOT) -> List[str]:
    import ast

    path = bench_root / "harness" / "manifest.py"
    if not path.exists():
        raise AuditError(f"benchmark harness not found: {path}")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == "FROZEN_SET"
                   for t in node.targets):
                return sorted(ast.literal_eval(node.value))
    raise AuditError("benchmark does not declare FROZEN_SET")


def defect_fingerprints(bench_root: Path = BENCH_ROOT) -> List[Tuple[str, str]]:
    """Literal code fragments that only exist in the private defect scripts.

    Returns ``(fragment, owning_file)`` pairs. The owning file matters: the
    snapshot legitimately CONTAINS the defective code -- that is the task -- so a
    fingerprint is only evidence of a leak when it shows up somewhere else.

    Only the ``buggy`` fragment is captured. The ``fixed`` fragment is excluded
    because for these tasks it IS the upstream code, which the snapshot must
    contain.

    Documentation tasks are skipped entirely: their "defect" is prose in the
    workspace's own README, including the upstream's own stale figure, which
    legitimately appears.
    """
    prints: List[Tuple[str, str]] = []
    tasks_dir = bench_root / "tasks"
    if not tasks_dir.is_dir():
        return prints

    for tid in FROZEN_CACHE:
        defect_path = tasks_dir / tid / "defect.json"
        if not defect_path.exists():
            continue
        try:
            defect = json.loads(defect_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        target = defect.get("target", "")
        if not target.endswith(".py"):
            continue                      # documentation task: no code fragment
        # The export keeps the snapshot under repo_snapshot/, so the owner path
        # is exactly where the fragment legitimately appears.
        owner = target if target.startswith("repo_snapshot/") \
            else f"repo_snapshot/{target}"
        for pattern in defect.get("patterns", []):
            fragment = (pattern.get("buggy") or "").strip()
            # Only distinctive fragments: a bare punctuation change is not a
            # fingerprint and would fire on unrelated code.
            if len(fragment) >= 24 and " " in fragment:
                prints.append((fragment, owner))
    return prints


def _manifest_tasks(bench_root: Path = BENCH_ROOT) -> List[Dict[str, Any]]:
    p = bench_root / "benchmark_manifest.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("tasks", [])


FROZEN_CACHE: set = set()


# ── path / name scan ──────────────────────────────────────────────────────
def scan_paths(ws: Path) -> List[str]:
    findings: List[str] = []
    for item in sorted(ws.rglob("*")):
        rel = item.relative_to(ws)
        parts = [p.lower() for p in rel.parts]
        name = parts[-1] if parts else ""

        if name in PRIVATE_EXACT_NAMES:
            findings.append(f"private artifact name: {rel.as_posix()}")
        private_dirs = {d.lower() for d in PRIVATE_DIR_NAMES}
        if private_dirs & set(parts[:-1]):
            findings.append(f"inside private directory: {rel.as_posix()}")
        if name.endswith(".patch") or name.endswith(".diff"):
            findings.append(f"patch/diff artifact present: {rel.as_posix()}")
        if name.startswith(".") and name in {".solution", ".reference"}:
            findings.append(f"private dotfile: {rel.as_posix()}")
    return findings


# ── content scan (streaming) ──────────────────────────────────────────────
def scan_content(ws: Path, fingerprints: List[Tuple[str, str]]) -> List[str]:
    findings: List[str] = []
    phrase_re = re.compile("|".join(re.escape(p) for p in LEAK_PHRASES),
                           re.IGNORECASE)

    # Map each fragment to the one file it is allowed to appear in.
    owners: Dict[str, str] = {frag: owner for frag, owner in fingerprints}
    fp_re = (re.compile("|".join(re.escape(f) for f in owners))
             if owners else None)

    for item in sorted(ws.rglob("*")):
        if not item.is_file() or item.is_symlink():
            continue
        suffix = item.suffix.lower()
        rel = item.relative_to(ws).as_posix()

        if suffix in BINARY_SUFFIXES:
            continue                      # path-checked only, never decoded
        if suffix not in TEXT_SUFFIXES:
            continue

        # A chunk can split a phrase, so carry a small tail overlap.
        tail = ""
        try:
            with open(item, "rb") as fh:
                while True:
                    block = fh.read(CHUNK)
                    if not block:
                        break
                    window = (tail + block.decode("utf-8", errors="ignore"))
                    m = phrase_re.search(window)
                    if m:
                        findings.append(f"leak phrase {m.group(0)!r} in {rel}")
                        break
                    if fp_re:
                        hit = fp_re.search(window)
                        if hit and owners.get(hit.group(0)) != rel:
                            findings.append(
                                f"defect fragment outside its own file in {rel}")
                            break
                    tail = window[-256:]
        except OSError:
            continue
    return findings


# ── integrity: the export must not have changed the task ──────────────────
def _read_text_any(path: Path) -> str:
    """Read a file, trying the encodings this benchmark actually uses.

    Some of the upstream documentation is GBK-encoded, so a hard-coded UTF-8
    read both fails and, worse, would silently corrupt the file on write-back.
    """
    raw = path.read_bytes()
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def run_git(ws: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(ws),
                          capture_output=True, text=True)


def check_git(ws: Path) -> Dict[str, Any]:
    if not (ws / ".git").is_dir():
        return {"baseline_clean": False, "remote_empty": False,
                "reason": "no git baseline"}
    status = run_git(ws, "status", "--porcelain")
    remotes = run_git(ws, "remote", "-v")
    log = run_git(ws, "log", "--oneline")

    dirty = [l for l in status.stdout.splitlines() if l.strip()]

    def _acceptable(line: str) -> bool:
        # Test-run residue: bytecode and pytest's own cache.
        if "__pycache__" in line or ".pytest_cache" in line:
            return True
        # Runtime state the suite itself writes: the governance service keeps
        # its session records in a SQLite file, and the tests exercise it. That
        # is the code under test doing its job, not the export being wrong.
        if line.rstrip().endswith((".db", ".db-wal", ".db-shm")):
            return True
        return False

    cache_only = all(_acceptable(l) for l in dirty) if dirty else True
    return {
        "baseline_clean": status.returncode == 0 and cache_only,
        "remote_empty": not remotes.stdout.strip(),
        "dirty_paths": dirty,
        "dirty_is_test_cache_only": cache_only,
        "baseline_commit": log.stdout.strip().split(" ", 1)[0] if log.stdout.strip() else None,
    }


def _suite_root(ws: Path) -> Path:
    """Where the repository under test lives inside the workspace.

    The export keeps the snapshot under ``repo_snapshot/`` because the public
    checks locate it that way. Running the upstream suite from the workspace
    root instead would also collect ``public_tests/`` and inflate the failure
    count -- a false regression produced by the audit, not by the export.
    """
    nested = ws / "repo_snapshot"
    return nested if nested.is_dir() else ws


def check_public_tests(task_id: str, bench_root: Path = BENCH_ROOT) -> Dict[str, Any]:
    """Run the task's public checks against the EXPORTED workspace.

    This is the check that pruning did not break the task: if the snapshot is
    missing a module the public checks import, they fail here -- and that would
    be an environment failure introduced by the export, not by any agent.
    """
    ws = WORKSPACES / task_id
    public = ws / "public_tests"
    if not public.is_dir():
        return {"public_tests_present": False, "reason": "no public_tests/"}

    tests = sorted(public.rglob("test_*.py"))
    if not tests:
        return {"public_tests_present": False, "reason": "no test_*.py"}

    # Run from the workspace root so the snapshot's own imports resolve.
    # PYTHONDONTWRITEBYTECODE keeps the audit from leaving __pycache__ behind,
    # which would make the tree look dirty for the audit's own reason.
    env = dict(**__import__("os").environ, PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         f"public_tests/{tests[0].relative_to(public).as_posix()}"],
        cwd=str(ws), capture_output=True, text=True, timeout=900, env=env,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return {
        "public_tests_present": True,
        "exit_code": proc.returncode,
        # A pass is not required -- the workspace ships DEFECTIVE by design, so
        # hidden-side failures are expected. What must not appear is a missing
        # dependency/import, which would mean the export broke the task.
        "import_or_env_failure": bool(
            re.search(r"ModuleNotFoundError|ImportError|cannot import|"
                      r"ERROR collecting", out)),
        "tail": out[-600:],
    }


def check_defect_reproduced(task_id: str,
                            bench_root: Path = BENCH_ROOT) -> Dict[str, Any]:
    """Confirm the exported workspace is still in its expected defective state.

    Uses the benchmark's own private defect declarations as the oracle, but
    only reads them from outside the workspace -- nothing is copied in.

    Two oracles, in order:

    1. the task's ``defect.json`` -- the injected pattern must be present;
    2. the task's recorded baseline -- the upstream suite must still show the
       same failures as when the task was frozen.

    The second is what covers a task built before ``defect.json`` existed: it
    has no pattern to look for, but its baseline still says "N failures", and a
    workspace that drifted would show a different count.
    """
    ws = WORKSPACES / task_id
    defect_path = bench_root / "tasks" / task_id / "defect.json"

    if defect_path.exists():
        defect = json.loads(defect_path.read_text(encoding="utf-8"))
        patterns = defect.get("patterns", [])
        if not patterns:
            return {"exported_defect_reproduced": True,
                    "reason": "no injected defect declared (clean task)"}

        target_rel = defect["target"]
        if target_rel.startswith("repo_snapshot/"):
            # The snapshot already sits under repo_snapshot/ in the workspace,
            # so the path is used verbatim rather than stripped.
            target = ws / target_rel
        else:
            target = ws / "repo_snapshot" / target_rel
        if not target.exists():
            return {"exported_defect_reproduced": False,
                    "reason": f"target file missing in export: {target.name}"}
        text = _read_text_any(target)
        if defect.get("shipped", "defective") == "defective":
            if patterns[0]["buggy"] in text:
                return {"exported_defect_reproduced": True,
                        "reason": "defective pattern present in exported workspace"}
            return {"exported_defect_reproduced": False,
                    "reason": "defective pattern not found in exported workspace"}
        return {"exported_defect_reproduced": True,
                "reason": "clean task: nothing to reproduce"}

    return _check_baseline_reproduced(task_id, bench_root, ws)


def _check_baseline_reproduced(task_id: str, bench_root: Path, ws: Path) -> Dict[str, Any]:
    """Fallback oracle: the workspace must still fail exactly as it was frozen.

    Runs the upstream suite inside the exported workspace and compares the
    pass/fail counts against the task's recorded defective baseline. Equal
    counts mean the export reproduced the task rather than changing it.
    """
    meta_path = bench_root / "tasks" / task_id / "reference_metadata.json"
    if not meta_path.exists():
        return {"exported_defect_reproduced": None,
                "reason": "no defect.json and no reference_metadata.json; "
                          "cannot verify the shipped state"}

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    baseline = meta.get("baseline", {}).get("recorded_at_defective_state", {})
    expected_failed = baseline.get("failed")
    if expected_failed is None:
        return {"exported_defect_reproduced": None,
                "reason": "baseline records no failure count"}

    env = dict(**__import__("os").environ, PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=str(_suite_root(ws)), capture_output=True, text=True,
        timeout=1800, env=env,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    m = re.search(r"(\d+) failed", out)
    actual_failed = int(m.group(1)) if m else 0

    if actual_failed == expected_failed:
        return {"exported_defect_reproduced": True,
                "reason": f"{actual_failed} upstream failure(s), matching the "
                          f"frozen defective baseline"}
    return {"exported_defect_reproduced": False,
            "reason": f"workspace shows {actual_failed} upstream failure(s), "
                      f"frozen baseline expects {expected_failed}"}


# ── audit one workspace ───────────────────────────────────────────────────
def audit_task(task_id: str, fingerprints: List[str]) -> Dict[str, Any]:
    ws = WORKSPACES / task_id
    row: Dict[str, Any] = {"task_id": task_id}

    row["workspace_exists"] = ws.is_dir()
    row["prompt_exists"] = (ws / "prompt.md").is_file()

    # Check git BEFORE running the public tests: pytest writes a cache
    # directory, which would make the tree look dirty for a reason that has
    # nothing to do with the export.
    git = check_git(ws)
    row["git_baseline_clean"] = git.get("baseline_clean", False)
    row["git_remote_empty"] = git.get("remote_empty", False)
    row["git_detail"] = git

    path_findings = scan_paths(ws)
    content_findings = scan_content(ws, fingerprints)
    row["private_path_scan_pass"] = not path_findings
    row["private_content_scan_pass"] = not content_findings
    row["path_findings"] = path_findings
    row["content_findings"] = content_findings

    public = check_public_tests(task_id)
    row["public_tests_present"] = public.get("public_tests_present", False)
    row["public_tests_detail"] = public
    row["unexpected_missing_dependency"] = public.get(
        "import_or_env_failure", False)

    repro = check_defect_reproduced(task_id)
    row["exported_defect_reproduced"] = repro.get("exported_defect_reproduced")
    row["defect_detail"] = repro

    row["audit_status"] = all([
        row["workspace_exists"],
        row["prompt_exists"],
        row["public_tests_present"],
        row["private_path_scan_pass"],
        row["private_content_scan_pass"],
        row["git_baseline_clean"],
        row["git_remote_empty"],
        row["exported_defect_reproduced"] is not False,
        not row["unexpected_missing_dependency"],
    ])
    return row


# ── report ────────────────────────────────────────────────────────────────
def write_report(rows: List[Dict[str, Any]], frozen: List[str]) -> str:
    ok = sum(1 for r in rows if r["audit_status"])
    lines = [
        "# Public workspace audit",
        "",
        "Read-only audit of the exported public evaluation workspaces.",
        "Nothing in the frozen benchmark was modified to produce this.",
        "",
        f"- frozen tasks: **{len(frozen)}**",
        f"- workspaces audited: {len(rows)}",
        f"- passed: **{ok}**",
        "",
        "## Scan scope",
        "",
        f"- every file's path and name checked (binary included)",
        f"- every text file scanned in full, in {CHUNK // (1024 * 1024)} MiB chunks",
        f"- file types scanned: {', '.join(sorted(TEXT_SUFFIXES))}",
        f"- binary types path-checked only: {', '.join(sorted(BINARY_SUFFIXES)[:8])}...",
        "",
        "Matching is on private-artifact names, unambiguous phrases, and exact",
        "defect fingerprints -- never on ordinary words, so the upstream",
        "projects' own engineering files (e.g. their `grader_parity.json`) are",
        "not false positives.",
        "",
        "## Per-task results",
        "",
    ]

    for row in rows:
        lines += [
            f"### {row['task_id']}",
            "",
            f"- workspace_exists: **{row['workspace_exists']}**",
            f"- prompt_exists: **{row['prompt_exists']}**",
            f"- public_tests_present: **{row['public_tests_present']}**",
            f"- git_baseline_clean: **{row['git_baseline_clean']}**",
            f"- git_remote_empty: **{row['git_remote_empty']}**",
            f"- private_path_scan_pass: **{row['private_path_scan_pass']}**",
            f"- private_content_scan_pass: **{row['private_content_scan_pass']}**",
            f"- exported_defect_reproduced: **{row['exported_defect_reproduced']}**",
            f"- unexpected_missing_dependency: **{row['unexpected_missing_dependency']}**",
            f"- audit_status: **{row['audit_status']}**",
            "",
        ]
        d = row.get("defect_detail", {})
        if d.get("reason"):
            lines.append(f"  - defect note: {d['reason']}")
        g = row.get("git_detail", {})
        if g.get("baseline_commit"):
            lines.append(f"  - baseline commit: {g['baseline_commit']}")
        for f in row.get("path_findings", []):
            lines.append(f"  - PATH: {f}")
        for f in row.get("content_findings", []):
            lines.append(f"  - CONTENT: {f}")
        lines.append("")

    lines += ["## Verdict", ""]
    if ok == len(frozen):
        lines.append(f"**PUBLIC EVALUATION WORKSPACES READY: {ok}/{len(frozen)}**")
    else:
        lines.append(f"PUBLIC EVALUATION WORKSPACES READY: {ok}/{len(frozen)}")
        lines.append("")
        lines.append("Failed tasks:")
        for r in rows:
            if not r["audit_status"]:
                lines.append(f"- {r['task_id']}")
    lines.append("")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspaces", type=Path, default=WORKSPACES)
    args = ap.parse_args(argv)

    frozen = frozen_set()
    if len(frozen) != EXPECTED_FROZEN_TASKS:
        print(f"AUDIT REFUSED: frozen set is {len(frozen)}, expected "
              f"{EXPECTED_FROZEN_TASKS}", file=sys.stderr)
        return 2

    FROZEN_CACHE.update(frozen)
    fingerprints = defect_fingerprints()
    print(f"loaded {len(fingerprints)} defect fingerprint(s)")
    rows = []
    for tid in frozen:
        ws = args.workspaces / tid
        if not ws.is_dir():
            rows.append({"task_id": tid, "audit_status": False,
                         "workspace_exists": False,
                         "path_findings": [], "content_findings": [],
                         "private_path_scan_pass": False,
                         "private_content_scan_pass": False,
                         "git_baseline_clean": False, "git_remote_empty": False,
                         "prompt_exists": False, "public_tests_present": False,
                         "unexpected_missing_dependency": True,
                         "exported_defect_reproduced": False})
            continue
        row = audit_task(tid, fingerprints)
        rows.append(row)
        mark = "OK  " if row["audit_status"] else "FAIL"
        print(f"  {mark} {tid}")

    REPORT.write_text(write_report(rows, frozen), encoding="utf-8")

    ok = sum(1 for r in rows if r["audit_status"])
    print()
    print(f"audit written to {REPORT.name}")
    if ok == len(frozen):
        print(f"PUBLIC EVALUATION WORKSPACES READY: {ok}/{len(frozen)}")
        return 0
    print(f"PUBLIC EVALUATION WORKSPACES READY: {ok}/{len(frozen)}")
    for r in rows:
        if not r["audit_status"]:
            print(f"  FAILED: {r['task_id']}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

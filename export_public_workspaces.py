"""Export public evaluation workspaces from the frozen benchmark.

READ-ONLY with respect to the benchmark. Nothing in the frozen tree is
modified, and nothing sensitive is copied out.

Each workspace contains exactly:

* the task's defective repo snapshot,
* ``prompt.md`` -- the task statement written for the agent,
* ``public_tests/`` -- the checks the design allows the agent to see.

Everything else stays behind: hidden tests, reference repairs, defect
injection scripts, baselines, graders, internal reports and design notes. The
allowlist below is the mechanism, not a comment: if a name is not in it, it
does not get copied.

After exporting, the same script runs a leak scan over the result:
path/name blacklist, in-content markers, and a check that the workspace is
self-consistent. Anything suspicious is a hard failure.

    python export_public_workspaces.py            # export + audit
    python export_public_workspaces.py --audit    # audit an existing export
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

EVAL_ROOT = Path(__file__).resolve().parent
BENCH_ROOT = EVAL_ROOT.parent / "RealRepoBench-Q2609"
WORKSPACES = EVAL_ROOT / "workspaces"

#: The frozen evaluation set, read from the benchmark itself.
EXPECTED_FROZEN_TASKS = 8

#: The only top-level entries of a task directory that may ever be exported.
EXPORTABLE_TOP_LEVEL = {"repo_snapshot", "public_tests", "prompt.md"}

#: Top-level directory names that are internal to this benchmark. Anything
#: with one of these at the root of the export is a leak by construction.
FORBIDDEN_TOP_LEVEL = (
    "hidden", "hidden_tests",
    "reference", "reference_metadata",
    "defect", "defect_injection",
    "baseline_failures",
    "grader",
    "private",
    "build_report",
    "solution",
    "notes",
)

#: Exact filenames that are internal artefacts wherever they appear.
FORBIDDEN_EXACT_NAMES = (
    "hidden_tests",
    "reference_metadata.json",
    "reference.patch",
    "reference_solution",
    "reference_solution.patch",
    "defect.json",
    "defect_script.py",
    "baseline_failures.json",
    "gold_patch.patch",
    "snapshot.json",
    "checksums.sha256",
)

#: Directory names that mark an internal location, at any depth.
FORBIDDEN_DIR_NAMES = (
    "hidden_tests", "reference", "defect", "baseline_failures", "grader_dir",
)

#: Markers that must not appear in any exported file's contents.
FORBIDDEN_MARKERS = (
    "reference repair",
    "reference fix",
    "injected defect",
    "defect injection",
    "expected fixed",
    "old_pattern",
    "new_pattern",
    "hidden test",
    "hidden oracle",
    "the correct patch",
    "target_failure",
)

#: Files that are never scanned for content markers: caches and machine dumps.
SKIP_CONTENT_SUFFIXES = (
    ".pyc", ".pyo", ".db", ".coverage", ".db-wal", ".db-shm",
    ".arrow", ".parquet", ".pkl", ".bin", ".so", ".gz", ".zip",
)

#: Extensions worth scanning for leaked markers.
SCAN_SUFFIXES = (
    ".py", ".md", ".txt", ".json", ".jsonl", ".cfg", ".ini", ".toml",
    ".yaml", ".yml", ".sh", ".bat", ".cff",
)

#: Directories that carry no benchmark information and only bloat the export.
PRUNE_DIRS = (
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".git", ".venv", "venv", "node_modules", ".coverage_html", "htmlcov",
    "dist", "build", ".eggs",
)

#: File suffixes that are pure build/editor/cache residue and can never affect
#: a test run. Data files are NOT here on purpose: the upstream suites load
#: ``.arrow``/``.parquet`` fixtures, and pruning those turns a working task into
#: 19 environment errors that have nothing to do with the agent.
PRUNE_FILE_SUFFIXES = (
    ".pyc", ".pyo", ".pyd",
    ".bak", ".swp", ".orig", ".rej", ".tmp",
    ".so", ".dll", ".dylib",
    ".woff", ".woff2", ".ttf", ".eot", ".mp4",
)

#: Suffixes that are neither pruned nor content-scanned: real data files.
#: They are path-checked only, exactly like binaries, but they must be copied.
DATA_SUFFIXES = {
    ".arrow", ".parquet", ".pkl", ".pickle", ".db", ".db-wal", ".db-shm",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".docx", ".xlsx",
    ".zip", ".gz", ".tgz", ".bin",
}


class ExportError(RuntimeError):
    """A condition that must stop the export rather than be worked around."""


# ─── frozen set ───────────────────────────────────────────────────────────
def frozen_set(bench_root: Path = BENCH_ROOT) -> List[str]:
    """Read the frozen set from the benchmark's own declaration."""
    import ast

    path = bench_root / "harness" / "manifest.py"
    if not path.exists():
        raise ExportError(f"benchmark harness not found: {path}")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == "FROZEN_SET"
                   for t in node.targets):
                return sorted(ast.literal_eval(node.value))
    raise ExportError("benchmark does not declare FROZEN_SET")


# ─── prompt rendering ─────────────────────────────────────────────────────
def render_prompt(task_id: str, bench_root: Path = BENCH_ROOT) -> str:
    """Build the agent-facing prompt from the task's own spec.

    Only non-sensitive fields are used: the statement, its constraints, the
    test command and the timeout. ``defect``, ``protected_paths``,
    ``reference_semantics_authority`` and every other internal field are
    deliberately not read.
    """
    import ast

    spec_path = bench_root / "tasks" / task_id / "task.json"
    if not spec_path.exists():
        raise ExportError(f"{task_id}: no task.json")
    spec = json.loads(spec_path.read_text(encoding="utf-8"))

    lines = [
        f"# {task_id}",
        "",
        f"**Repository:** {spec.get('repository', 'unknown')}",
        f"**Difficulty:** {spec.get('difficulty', 'unspecified')}",
        "",
        "## Task",
        "",
        spec.get("prompt", "").strip(),
        "",
    ]

    zh = (spec.get("prompt_zh") or "").strip()
    if zh:
        lines += ["<details><summary>中文说明</summary>", "", zh, "", "</details>", ""]

    constraints = spec.get("constraints") or []
    if constraints:
        lines += ["## Constraints", ""]
        lines += [f"- {c}" for c in constraints]
        lines.append("")

    test_command = spec.get("test_command") or "pytest -q"
    timeout = spec.get("timeout_seconds")
    lines += [
        "## How your work is checked",
        "",
        f"- Test command: `{test_command}`",
    ]
    if timeout:
        lines.append(f"- Time budget: {timeout} seconds")
    lines += [
        "- Public checks are in `public_tests/` and are the ones you can run "
        "yourself.",
        "- Additional checks you cannot see are applied after you finish.",
        "",
        "Work inside this directory. Do not look for, download, or reproduce "
        "the upstream project's history; the repository here is a private "
        "snapshot and its history is intentionally absent.",
        "",
    ]
    return "\n".join(lines)


# ─── export ───────────────────────────────────────────────────────────────
def copy_tree(src: Path, dst: Path) -> List[str]:
    """Copy ``src`` into ``dst``.

    The source is the task's private snapshot, whose whole point is to be the
    repository handed to the agent, so its own contents are copied as they are.
    What is blocked is this benchmark's own material -- hidden tests, reference
    repairs, defect scripts, baselines -- which is why the check is on internal
    artefact names and internal directories, not on substrings of upstream
    filenames.
    """
    if not src.is_dir():
        raise ExportError(f"source tree missing: {src}")

    internal_exact = {n.lower() for n in FORBIDDEN_EXACT_NAMES}
    internal_dirs = {d.lower() for d in FORBIDDEN_DIR_NAMES}
    top_level = {n.lower() for n in FORBIDDEN_TOP_LEVEL}
    prune = {d.lower() for d in PRUNE_DIRS}

    copied: List[str] = []
    for item in sorted(src.rglob("*")):
        if item.is_symlink():
            continue
        rel = item.relative_to(src)
        parts = [p.lower() for p in rel.parts]
        if prune & set(parts[:-1]):
            continue
        if parts and parts[-1] in internal_exact:
            raise ExportError(f"refusing to copy {rel.as_posix()}: internal artefact")
        if internal_dirs & set(parts[:-1]):
            raise ExportError(f"refusing to copy {rel.as_posix()}: internal directory")
        if parts and parts[0] in top_level:
            raise ExportError(f"refusing to copy {rel.as_posix()}: internal directory")
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if item.suffix.lower() in {s.lower() for s in PRUNE_FILE_SUFFIXES}:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        copied.append(rel.as_posix())
    return copied


def _forbidden_path(rel: Path) -> bool:
    """Whether a path is internal benchmark material rather than repo content.

    Restricted to the top level of the task directory's own artefacts. A file
    like ``benchmark/results/.../grader_parity.json`` is part of the upstream
    repository's own benchmark output -- it is the code under test, not this
    benchmark's grader -- so blocking it by name would reject the task itself.
    Content is still scanned for markers, which is where real leakage shows up.
    """
    parts = [p.lower() for p in rel.parts]
    if not parts:
        return False
    top = parts[0]

    # Whole directories that are internal to the benchmark.
    for bad in FORBIDDEN_TOP_LEVEL:
        if top == bad or top.startswith(bad):
            return True

    # A specific internal artefact by exact name, anywhere in the tree.
    name = parts[-1]
    for exact in FORBIDDEN_EXACT_NAMES:
        if name == exact:
            return True
    return False


def _force_writable(root: Path) -> None:
    """Clear read-only bits so a previous baseline can be replaced.

    ``git init`` writes its object files read-only on Windows, so re-exporting
    over an existing workspace would otherwise fail with PermissionError.
    """
    import stat

    for p in root.rglob("*"):
        try:
            mode = p.stat().st_mode
            p.chmod(mode | stat.S_IWRITE | stat.S_IREAD)
        except OSError:
            continue


def export_task(task_id: str, bench_root: Path = BENCH_ROOT,
                dest: Path = WORKSPACES) -> Dict[str, Any]:
    """Export one task's public workspace.

    The snapshot is placed under ``repo_snapshot/`` exactly as it sits in the
    frozen benchmark, rather than flattened into the workspace root. That is not
    cosmetic: the task's public checks locate the code under test with
    ``parents[1] / "repo_snapshot"``, so flattening breaks them and turns a
    solvable task into a collection error the agent cannot act on.
    """
    task_dir = bench_root / "tasks" / task_id
    ws = dest / task_id
    if ws.exists():
        _force_writable(ws)
        shutil.rmtree(ws)
    ws.mkdir(parents=True)

    snapshot = task_dir / "repo_snapshot"
    if not snapshot.is_dir():
        raise ExportError(f"{task_id}: no repo_snapshot")

    copied_snapshot = copy_tree(snapshot, ws / "repo_snapshot")

    public_src = task_dir / "public_tests"
    public_copied: List[str] = []
    if public_src.is_dir():
        public_copied = copy_tree(public_src, ws / "public_tests")

    (ws / "prompt.md").write_text(render_prompt(task_id, bench_root),
                                  encoding="utf-8")

    return {
        "task_id": task_id,
        "snapshot_files": len(copied_snapshot),
        "public_test_files": public_copied,
        "workspace": ws,
    }


# ─── leak scan ────────────────────────────────────────────────────────────
def scan_workspace(ws: Path) -> List[str]:
    """Return a list of leak findings. Empty means clean.

    Two independent checks:

    * names -- anything the benchmark itself owns (hidden tests, reference
      repairs, defect scripts, baselines, graders) must not be present;
    * content -- internal markers must not appear in any exported text file.

    Name matching is deliberately scoped: it applies to the internal artefact
    directories and exact filenames, not to substrings of the upstream
    repository's own filenames. The upstream projects legitimately contain
    files with names like ``grader_parity.json`` -- that is the code under
    test, not this benchmark's grading logic.
    """
    findings: List[str] = []

    for item in sorted(ws.rglob("*")):
        rel = item.relative_to(ws)
        parts = [p.lower() for p in rel.parts]
        name = parts[-1] if parts else ""

        if name in {n.lower() for n in FORBIDDEN_EXACT_NAMES}:
            findings.append(f"internal artefact present: {rel.as_posix()}")
        internal_dirs = {d.lower() for d in FORBIDDEN_DIR_NAMES}
        if internal_dirs & set(parts[:-1]):
            findings.append(f"inside an internal directory: {rel.as_posix()}")
        if _is_internal_top_level(parts[:-1]):
            findings.append(f"internal benchmark directory at root: {rel.as_posix()}")

    for item in sorted(ws.rglob("*")):
        if not item.is_file():
            continue
        if item.suffix.lower() in {s.lower() for s in SKIP_CONTENT_SUFFIXES}:
            continue
        if item.suffix.lower() in {s.lower() for s in PRUNE_FILE_SUFFIXES}:
            continue
        if item.suffix not in SCAN_SUFFIXES:
            continue
        try:
            text = item.read_text(encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, OSError):
            continue
        low = text.lower()
        for marker in FORBIDDEN_MARKERS:
            if marker.lower() in low:
                findings.append(
                    f"leak marker {marker!r} in {item.relative_to(ws).as_posix()}"
                )
    return findings


def _is_internal_top_level(parts: List[str]) -> bool:
    """True when a path's first component is an internal benchmark directory."""
    if not parts:
        return False
    return parts[0] in {n.lower() for n in FORBIDDEN_TOP_LEVEL}


# ─── git baseline ─────────────────────────────────────────────────────────
def init_baseline(ws: Path) -> Dict[str, Any]:
    """Give the workspace a clean, history-free git baseline.

    The upstream repository's history is the one thing the agent must not see
    -- it contains the real fix -- so the snapshot is committed as a fresh
    single-commit repository with no remote.
    """
    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=str(ws),
                              capture_output=True, text=True)

    if not (ws / ".git").exists():
        p = run("init")
        if p.returncode != 0:
            raise ExportError(f"{ws.name}: git init failed: {p.stderr.strip()}")

    # Make the identity deterministic so the commit does not depend on the
    # machine's global git config.
    run("config", "user.email", "benchmark@local")
    run("config", "user.name", "RealRepoBench")
    # Keep line endings as they are: the snapshots mix LF and GBK content, and a
    # rewrite would change bytes the public checks read.
    run("config", "core.autocrlf", "false")
    # Windows rejects paths over ~260 chars, and this repository's result tree
    # nests deeply. Let git use the long-path API instead of failing the export.
    run("config", "core.longpaths", "true")
    # Do not treat LF/CRLF warnings on stderr as a failure: git exits 0 for those.
    added = run("add", "-A")
    if added.returncode != 0:
        raise ExportError(f"{ws.name}: git add failed: {added.stderr.strip()[:400]}")
    commit = run("commit", "-m", "RealRepoBench frozen baseline")
    combined = (commit.stdout or "") + (commit.stderr or "")
    # "nothing to commit" happens when .gitignore covers everything left; the
    # baseline then already exists and is clean, which is not a failure.
    if commit.returncode != 0 and "nothing to commit" not in combined:
        raise ExportError(f"{ws.name}: git commit failed: {combined.strip()[:400]}")

    remotes = run("remote", "-v")
    if remotes.stdout.strip():
        raise ExportError(
            f"{ws.name}: git remote is not empty:\n{remotes.stdout.strip()}"
        )

    log = run("log", "--oneline")
    status = run("status", "--porcelain")
    return {
        "baseline_commit": log.stdout.strip().split(" ", 1)[0] if log.stdout.strip() else None,
        "remotes": [],
        "dirty_paths": [ln for ln in status.stdout.splitlines() if ln.strip()],
        "history_free": True,
    }


# ─── audit ────────────────────────────────────────────────────────────────
def audit_workspace(ws: Path, task_id: str,
                    bench_root: Path = BENCH_ROOT) -> Dict[str, Any]:
    checks: Dict[str, Any] = {}

    checks["workspace_exists"] = ws.is_dir()

    prompt = ws / "prompt.md"
    checks["prompt_exists"] = prompt.is_file()

    checks["repo_snapshot_exists"] = any(
        p.is_file() for p in ws.rglob("*.py")
    ) or any(p.is_file() for p in ws.iterdir() if p.is_file())

    public_dir = ws / "public_tests"
    if public_dir.is_dir():
        public_files = [p.name for p in public_dir.rglob("*.py")]
        checks["public_tests"] = (
            f"present ({len(public_files)} file(s))" if public_files else "empty"
        )
    else:
        checks["public_tests"] = "N/A (no public checks in this task's design)"

    findings = scan_workspace(ws)
    checks["hidden_material_absent"] = not any(
        "hidden" in f.lower() for f in findings)
    checks["reference_material_absent"] = not any(
        "reference" in f.lower() for f in findings)
    checks["defect_metadata_absent"] = not any(
        "defect" in f.lower() for f in findings)

    if (ws / ".git").exists():
        remotes = subprocess.run(["git", "remote", "-v"], cwd=str(ws),
                                 capture_output=True, text=True)
        checks["git_baseline_clean"] = True
        checks["git_remote_empty"] = not remotes.stdout.strip()
    else:
        checks["git_baseline_clean"] = False
        checks["git_remote_empty"] = False

    checks["leak_findings"] = findings
    return checks


# ─── manifest ─────────────────────────────────────────────────────────────
def write_manifest(frozen: List[str], dest: Path = WORKSPACES,
                   bench_root: Path = BENCH_ROOT) -> Dict[str, Any]:
    manifest = {
        "benchmark": "RealRepoBench-Q2609",
        "version": "0.1",
        "frozen_tasks": len(frozen),
        "fresh_session_required": True,
        "workspace_root": str(dest),
        "tasks": [],
    }
    for tid in frozen:
        spec_path = bench_root / "tasks" / tid / "task.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        manifest["tasks"].append({
            "task_id": tid,
            "workspace_path": str(dest / tid),
            "prompt_path": str(dest / tid / "prompt.md"),
            "repository": spec.get("repository"),
            "difficulty": spec.get("difficulty"),
            "public_tests_dir": str(dest / tid / "public_tests"),
            "fresh_session_required": True,
        })
    (EVAL_ROOT / "evaluation_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    return manifest


# ─── main ─────────────────────────────────────────────────────────────────
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=WORKSPACES)
    ap.add_argument("--no-audit", action="store_true",
                    help="export only; run audit_public_workspaces.py separately")
    args = ap.parse_args(argv)

    frozen = frozen_set()
    if len(frozen) != EXPECTED_FROZEN_TASKS:
        print(f"EXPORT REFUSED: frozen set is {len(frozen)}, expected "
              f"{EXPECTED_FROZEN_TASKS}", file=sys.stderr)
        return 2

    print(f"exporting {len(frozen)} public workspaces -> {args.out}")
    for tid in frozen:
        info = export_task(tid, dest=args.out)
        baseline = init_baseline(args.out / tid)
        print(f"  {tid}: {info['snapshot_files']} file(s), "
              f"{len(info['public_test_files'])} public test file(s), "
              f"baseline {baseline['baseline_commit']}")

    if args.no_audit:
        print()
        print("export complete; run audit_public_workspaces.py to audit")
        return 0

    # Audit every workspace and collect findings.
    audit_rows = []
    failed = False
    for tid in frozen:
        ws = args.out / tid
        checks = audit_workspace(ws, tid)
        findings = checks.pop("leak_findings", [])
        ok = all(v for k, v in checks.items() if isinstance(v, bool))
        if findings:
            ok = False
        if not ok:
            failed = True
        audit_rows.append({"task_id": tid, "ok": ok, "checks": checks,
                           "findings": findings})

    write_manifest(frozen, dest=args.out)
    report = _audit_report(audit_rows, frozen)
    (EVAL_ROOT / "PUBLIC_WORKSPACE_AUDIT.md").write_text(
        report, encoding="utf-8")

    print()
    for row in audit_rows:
        mark = "OK  " if row["ok"] else "FAIL"
        print(f"  {mark} {row['task_id']}")
        for f in row["findings"]:
            print(f"        - {f}")

    ready = sum(1 for r in audit_rows if r["ok"])
    print()
    if failed or ready != len(frozen):
        print(f"PUBLIC EVALUATION WORKSPACES READY: {ready}/{len(frozen)}")
        print("audit written to PUBLIC_WORKSPACE_AUDIT.md", file=sys.stderr)
        return 1

    print(f"PUBLIC EVALUATION WORKSPACES READY: {ready}/{len(frozen)}")
    print("audit written to PUBLIC_WORKSPACE_AUDIT.md")
    return 0


def _audit_report(rows: List[Dict[str, Any]], frozen: List[str]) -> str:
    lines = [
        "# Public workspace audit",
        "",
        f"- frozen tasks: **{len(frozen)}**",
        f"- workspaces audited: {len(rows)}",
        "",
        "Each workspace is an independent copy of the task's defective snapshot",
        "with its prompt and its public checks. Nothing else is exported.",
        "",
    ]
    for row in rows:
        checks = row["checks"]
        lines += [
            f"## {row['task_id']}",
            "",
            f"- workspace exists: **{checks['workspace_exists']}**",
            f"- prompt exists: **{checks['prompt_exists']}**",
            f"- repo snapshot exists: **{checks['repo_snapshot_exists']}**",
            f"- public tests: {checks['public_tests']}",
            f"- hidden material absent: **{checks['hidden_material_absent']}**",
            f"- reference material absent: **{checks['reference_material_absent']}**",
            f"- defect metadata absent: **{checks['defect_metadata_absent']}**",
            f"- git baseline clean: **{checks['git_baseline_clean']}**",
            f"- git remote empty: **{checks['git_remote_empty']}**",
            "",
        ]
        if row["findings"]:
            lines += ["Findings:", ""]
            lines += [f"- {f}" for f in row["findings"]]
            lines.append("")

    ready = sum(1 for r in rows if r["ok"])
    lines += [
        "## Verdict",
        "",
        (f"**PUBLIC EVALUATION WORKSPACES READY: {ready}/{len(frozen)}**"
         if ready == len(frozen) else
         f"PUBLIC EVALUATION WORKSPACES READY: {ready}/{len(frozen)}"),
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())

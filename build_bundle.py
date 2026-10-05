"""Assemble the submission evidence bundle.

Read-only with respect to the benchmark and the workspaces. Everything is
COPIED into ``submission_bundle/``; nothing is moved or edited.

Secret hygiene is enforced, not assumed: any path whose name matches a
credential pattern is refused, and the bundle is scanned afterwards so a leak
cannot slip in through an unexpected filename.

    python build_bundle.py
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List

EVAL_ROOT = Path(__file__).resolve().parent
BENCH = EVAL_ROOT.parent / "RealRepoBench-Q2609"
BUNDLE = EVAL_ROOT / "submission_bundle"
RUNS = EVAL_ROOT / "evaluation_runs"
RESULTS = EVAL_ROOT / "results"

ORDERED = [
    "RB-AS-001", "RB-AS-002", "RB-AS-003", "RB-AS-004", "RB-AS-005",
    "RB-EM-001", "RB-EM-002", "RB-EM-004",
]

#: Anything matching one of these is refused, by filename or by path component.
SECRET_PATTERNS = re.compile(
    r"(^|/)(\.env($|\.)|.*\.pem$|.*\.key$|.*\.p12$|.*\.pfx$|"
    r"id_rsa.*|id_ed25519.*|credentials($|\.)|\.netrc$|\.npmrc$|"
    r".*secret.*|.*token.*\.json$|secrets?\.(json|ya?ml|txt)$)",
    re.IGNORECASE,
)

#: Content that must never appear in the bundle.
SECRET_CONTENT = re.compile(
    r"(sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|"
    r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"xox[baprs]-[A-Za-z0-9-]{10,})"
)

#: Scoring scratch and embargoed material that must never be published. A
#: grading run legitimately produces these on the operator's machine; publishing
#: them would disclose the hidden checks and their failure output to the model
#: under test. They remain in ``evaluation_runs/`` as operator-side evidence and
#: are simply not carried into the submission bundle.
FORBIDDEN_BUNDLE_NAMES = re.compile(
    r"(^|/)(_staging|hidden_tests?(\.[^/]*)?|staging|scratch|tmp|"
    r"grader_stdout(\.[^/]*)?)(/|$)",
    re.IGNORECASE,
)


class BundleError(RuntimeError):
    pass


def _copy(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)


def _copy_tree_safe(src: Path, dst: Path) -> List[str]:
    """Copy a tree, refusing anything whose name looks like a credential."""
    if not src.exists():
        return []
    copied: List[str] = []
    skipped: List[str] = []
    for item in sorted(src.rglob("*")):
        rel = item.relative_to(src).as_posix()
        if SECRET_PATTERNS.search(f"/{rel}") or SECRET_PATTERNS.search(rel):
            raise BundleError(f"refusing to bundle {rel}: matches a secret pattern")
        if FORBIDDEN_BUNDLE_NAMES.search(f"/{rel}"):
            # Not an error: these are known operator-side artifacts that must
            # stay in evaluation_runs/ but must not be published. Skipping is
            # the documented behaviour, so record it rather than abort.
            skipped.append(rel)
            continue
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if item.is_symlink():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        copied.append(rel)
    return copied + [f"[skipped] {s}" for s in skipped]


def scan_bundle_for_secrets(root: Path) -> List[str]:
    findings: List[str] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if SECRET_PATTERNS.search(f"/{rel}"):
            findings.append(f"secret-like filename: {rel}")
        if FORBIDDEN_BUNDLE_NAMES.search(f"/{rel}"):
            findings.append(f"embargoed or scratch material: {rel}")
        if p.suffix.lower() in {".pyc", ".db", ".png", ".zip", ".gz"}:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        m = SECRET_CONTENT.search(text)
        if m:
            findings.append(f"secret-like content in {rel} ({m.group(0)[:12]}...)")
    return findings


def build() -> Dict[str, Any]:
    if BUNDLE.exists():
        shutil.rmtree(BUNDLE)
    BUNDLE.mkdir(parents=True)

    # ── 01_benchmark ──────────────────────────────────────────────────────
    bench_out = BUNDLE / "01_benchmark"
    _copy(BENCH / "benchmark_manifest.json", bench_out / "benchmark_manifest.json")
    _copy(BENCH / "tasks.jsonl", bench_out / "tasks.jsonl")
    _copy(BENCH / "checksums.sha256", bench_out / "checksums.sha256")
    _copy(BENCH / "README.md", bench_out / "README.md")

    # ── 02_execution ──────────────────────────────────────────────────────
    _copy_tree_safe(RUNS, BUNDLE / "02_execution" / "evaluation_runs")

    # ── 03_results ────────────────────────────────────────────────────────
    res_out = BUNDLE / "03_results"
    for name in ("results.csv", "summary.json", "failure_cases.jsonl"):
        _copy(RESULTS / name, res_out / name)
    _copy(EVAL_ROOT / "EVALUATION_STATUS.json", res_out / "EVALUATION_STATUS.json")
    _copy(EVAL_ROOT / "REVERIFICATION.json", res_out / "REVERIFICATION.json")
    _copy(EVAL_ROOT / "PUBLIC_WORKSPACE_AUDIT.md",
          res_out / "PUBLIC_WORKSPACE_AUDIT.md")

    # ── 04_harness_reliability ────────────────────────────────────────────
    hz_out = BUNDLE / "04_harness_reliability"
    _copy(RUNS / "RB-AS-004" / "HARNESS_FAILURE.md",
          hz_out / "RB-AS-004_HARNESS_FAILURE.md")
    _copy(EVAL_ROOT / "HARNESS_RELIABILITY.md",
          hz_out / "HARNESS_RELIABILITY.md")

    # ── 05_environment ────────────────────────────────────────────────────
    env_out = BUNDLE / "05_environment"
    _copy(EVAL_ROOT / "evaluation_manifest.json",
          env_out / "evaluation_manifest.json")
    _copy(EVAL_ROOT / "README.md", env_out / "evaluation_README.md")
    _write_environment(env_out)

    return {"bundle": str(BUNDLE)}


def _write_environment(env_out: Path) -> None:
    import platform
    import sys as _sys

    from importlib.metadata import version, PackageNotFoundError

    def _v(mod: str) -> str:
        try:
            return version(mod)
        except PackageNotFoundError:
            return "not recorded"

    meta = {
        "python": _sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "pytest": _v("pytest"),
        "benchmark": "RealRepoBench-Q2609 v0.1",
        "frozen_tasks": 8,
        "model_under_test": "qwen-latest-series-invite-2609",
        "harness": "Qoder",
        "note": (
            "Environment recorded from the machine that performed the grading. "
            "No API keys, tokens, or credentials are included anywhere in this "
            "bundle; the build refuses secret-like filenames and scans the "
            "result for secret-like content."
        ),
    }
    (env_out / "environment.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    try:
        info = build()
    except BundleError as e:
        print(f"BUNDLE REFUSED: {e}", file=sys.stderr)
        return 2

    findings = scan_bundle_for_secrets(BUNDLE)
    if findings:
        print("BUNDLE REFUSED — secret-like material found:", file=sys.stderr)
        for f in findings:
            print("  -", f, file=sys.stderr)
        return 2

    print(f"bundle written to {info['bundle']}")
    total = sum(1 for _ in BUNDLE.rglob("*") if _.is_file())
    print(f"files bundled: {total}")
    print("secret scan: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

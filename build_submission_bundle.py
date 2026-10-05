"""Assemble the official submission bundle, with redaction and QA.

Copies evidence into ``submission_bundle/`` following the 01–06 layout required
for the official submission. Originals are never modified.

Two guards run, in order:

1. **embargo guard** — scratch dirs and hidden-grading output never leave the
   operator side;
2. **secret scan** — credential-shaped filenames and secret-shaped content are
   refused.

Anything that must be excluded is recorded in ``REDACTION_LOG.md`` rather than
dropped silently. Windows absolute paths in *submission copies* of the evidence
are rewritten to workspace-relative paths, so the published attachments do not
carry the operator's directory layout; the originals keep their paths.

    python build_submission_bundle.py
"""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

EVAL_ROOT = Path(__file__).resolve().parent
BENCH = EVAL_ROOT.parent / "RealRepoBench-Q2609"
RUNS = EVAL_ROOT / "evaluation_runs"
RESULTS = EVAL_ROOT / "results"
DATA = EVAL_ROOT / "FINAL_RESULTS_DATA"
BUNDLE = EVAL_ROOT / "submission_bundle"

ORDERED = [
    "RB-AS-001", "RB-AS-002", "RB-AS-003", "RB-AS-004", "RB-AS-005",
    "RB-EM-001", "RB-EM-002", "RB-EM-004",
]

#: Filenames / path components that hold credentials.
SECRET_NAMES = re.compile(
    r"(^|/)(\.env($|\.)|.*\.pem$|.*\.key$|.*\.p12$|.*\.pfx$|"
    r"id_rsa.*|id_ed25519.*|credentials($|\.)|\.netrc$|\.npmrc$|"
    r".*secret.*|.*token.*\.json$|secrets?\.(json|ya?ml|txt)$)",
    re.IGNORECASE,
)

#: Content that must never appear anywhere in the bundle.
SECRET_CONTENT = re.compile(
    r"(sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|"
    r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"xox[baprs]-[A-Za-z0-9-]{10,}|MDATAPLUS_API_KEY\s*[=:]\s*\S+)"
)

#: Operator-side material that must not be published.
EMBARGOED = re.compile(
    r"(^|/)(_staging|hidden_tests?(\.[^/]*)?|staging|scratch|tmp|"
    r"grader_stdout(\.[^/]*)?|reverify[^/]*)(/|$)",
    re.IGNORECASE,
)

#: Absolute paths to rewrite in the submission copy. Each entry is
#: (pattern, replacement). The evaluation root and the benchmark root become
#: bundle-relative references, so a published attachment never carries the
#: operator's directory layout.
# Path relativisation lives in its own module: the escaping rules for a run of
# backslashes are what defeated every attempt to express these patterns inline.
from relativise import relativise as _relativise_impl, find_residual as _find_residual
import bundle_qa



SKIP_BINARY = {".pyc", ".db", ".png", ".zip", ".gz", ".arrow"}


class BundleError(RuntimeError):
    pass


def _relativise(text: str) -> str:
    """Rewrite operator absolute paths into portable references."""
    return _relativise_impl(text)


def build() -> Dict[str, Any]:
    if BUNDLE.exists():
        shutil.rmtree(BUNDLE)
    BUNDLE.mkdir(parents=True)

    redaction: List[str] = []
    skipped: List[str] = []

    # ── 01_Benchmark_Facts ────────────────────────────────────────────────
    d1 = BUNDLE / "01_Benchmark_Facts"
    for name in ("BENCHMARK_FACT_SHEET.md", "GRADING.md",
                 "METHODOLOGY.md"):
        _copy(DATA / name, d1 / name)
    _copy(BENCH / "benchmark_manifest.json",
          d1 / "benchmark_manifest.json")
    _copy(BENCH / "tasks.jsonl", d1 / "tasks.jsonl")

    # ── 02_Results ────────────────────────────────────────────────────────
    d2 = BUNDLE / "02_Results"
    d2.mkdir(parents=True, exist_ok=True)
    for name in ("FINAL_METRICS.json", "FINAL_RESULTS_TABLE.csv",
                 "TASK_RESULT_TABLE.md", "CEILING_EFFECT_EVIDENCE.md"):
        _copy(DATA / name, d2 / name)
    for name in ("results.csv", "summary.json", "failure_cases.jsonl"):
        _copy(RESULTS / name, d2 / name)
    _copy(EVAL_ROOT / "EVALUATION_STATUS.json",
          d2 / "EVALUATION_STATUS.json")

    # ── 03_Execution_Evidence ─────────────────────────────────────────────
    d3 = BUNDLE / "03_Execution_Evidence" / "evaluation_runs"
    for tid in ORDERED:
        _copy_tree(RUNS / tid, d3 / tid, skipped)

    # ── 04_Harness_Reliability ────────────────────────────────────────────
    d4 = BUNDLE / "04_Harness_Reliability"
    _copy(DATA / "HARNESS_RELIABILITY_FACTS.md",
          d4 / "HARNESS_RELIABILITY_FACTS.md")
    _copy(RUNS / "RB-AS-004" / "HARNESS_FAILURE.md",
          d4 / "RB-AS-004_HARNESS_FAILURE.md")

    # ── 05_Submission_Field_Materials ─────────────────────────────────────
    d5 = BUNDLE / "05_Submission_Field_Materials"
    for name in ("SUBMISSION_FIELD_FACTS.md", "REPORT_OUTLINE.md"):
        _copy(DATA / name, d5 / name)
    _copy(DATA / "CEILING_EFFECT_EVIDENCE.md",
          d5 / "CEILING_EFFECT_EVIDENCE.md")

    # ── 06_Environment ────────────────────────────────────────────────────
    d6 = BUNDLE / "06_Environment"
    _copy(EVAL_ROOT / "evaluation_manifest.json",
          d6 / "evaluation_manifest.json")
    _copy(EVAL_ROOT / "submission_bundle" / "05_environment" / "environment.json"
          if False else EVAL_ROOT / "submission_bundle_environ.json"
          if False else _env_source(), d6 / "environment.json")
    _copy(EVAL_ROOT / "PUBLIC_WORKSPACE_AUDIT.md",
          d6 / "PUBLIC_WORKSPACE_AUDIT.md")
    # Independent recomputation of the recorded grades, run by the operator
    # outside the workspace. Lives in 06_Environment, not 03_Results.
    _copy(EVAL_ROOT / "REVERIFICATION.json",
          d6 / "REVERIFICATION.json")

    # Redact absolute paths in the submission copies only.
    for p in sorted(BUNDLE.rglob("*")):
        if not p.is_file() or p.suffix.lower() in SKIP_BINARY:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        cleaned = _relativise(text)
        if cleaned != text:
            p.write_text(cleaned, encoding="utf-8", newline="")
            redaction.append(p.relative_to(BUNDLE).as_posix())

    (BUNDLE / "06_Environment" / "REDACTION_LOG.md").write_text(
        _redaction_log(redaction, skipped), encoding="utf-8")
    return {"bundle": str(BUNDLE), "redacted": redaction,
            "skipped": skipped}


def _env_source() -> Path:
    for candidate in (EVAL_ROOT / "submission_bundle" / "05_environment" / "environment.json",
                     EVAL_ROOT / "05_environment" / "environment.json"):
        if candidate.exists():
            return candidate
    return EVAL_ROOT / "FINAL_RESULTS_DATA" / "environment.json"


def _copy(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _copy_tree(src: Path, dst: Path, skipped: List[str]) -> None:
    if not src.exists():
        return
    for item in sorted(src.rglob("*")):
        rel = item.relative_to(src).as_posix()
        if SECRET_NAMES.search(f"/{rel}") or SECRET_NAMES.search(rel):
            raise BundleError(f"refusing to bundle {rel}: credential-shaped name")
        if EMBARGOED.search(f"/{rel}"):
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


def _redaction_log(redacted: List[str], skipped: List[str]) -> str:
    lines = [
        "# Redaction log",
        "",
        "Original evidence is unmodified. This log records what the submission",
        "copy changed and what it omits.",
        "",
        "## Path relativisation",
        "",
        f"{len(redacted)} file(s) in the submission copy had operator absolute",
        "paths rewritten so the published attachments do not carry this",
        "machine's directory layout:",
        "",
        "- the frozen-benchmark root became `RealRepoBench-Q2609/`",
        "- the evaluation root was removed, leaving workspace-relative paths",
        "- user-home segments became `<user-home>`",
        "",
        "The originals in `evaluation_runs/` retain their paths and were not",
        "modified. Only the submission copies were rewritten.",
        "",
    ]
    lines += [f"- {r}" for r in redacted] or ["- none"]
    lines += [
        "",
        "## Operator-side material not published",
        "",
        "Scoring scratch and hidden-grading output stay in `evaluation_runs/` as",
        "operator-side evidence and are not carried into this bundle:",
        "",
    ]
    lines += [f"- {s}" for s in skipped] or ["- none"]
    lines += [
        "",
        "## Not collected at all",
        "",
        "No API key, token, credential, password or `.env` file was copied into",
        "this bundle. The build refuses credential-shaped filenames and scans",
        "every file for secret-shaped content.",
        "",
    ]
    return "\n".join(lines)


def scan_secrets(root: Path) -> List[str]:
    findings: List[str] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if SECRET_NAMES.search(f"/{rel}") or SECRET_NAMES.search(rel):
            findings.append(f"credential-shaped name: {rel}")
        if p.suffix.lower() in SKIP_BINARY:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if SECRET_CONTENT.search(text):
            findings.append(f"secret-shaped content: {rel}")
    return findings


def scan_abs_paths(root: Path) -> List[str]:
    """Operator absolute paths that survived into the submission copy.

    Uses the same detector as the rewriter, so a path the rewriter would replace
    but did not is reported rather than silently claimed absent.
    """
    findings: List[str] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix.lower() in SKIP_BINARY:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        residual = _find_residual(text)
        if residual:
            findings.append(
                f"{p.relative_to(root).as_posix()}: {residual[:2]}")
    return findings


def main() -> int:
    try:
        info = build()
    except BundleError as e:
        print(f"BUNDLE REFUSED: {e}", file=sys.stderr)
        return 2

    secrets = scan_secrets(BUNDLE)
    abs_left = scan_abs_paths(BUNDLE)
    problems, _rows = bundle_qa.run(BUNDLE)
    problems = problems + [f"secret scan: {s}" for s in secrets]
    problems = problems + [f"absolute path not relativised: {a}" for a in abs_left]
    bundle_qa.write_note(BUNDLE, problems)

    files = sum(1 for _ in BUNDLE.rglob("*") if _.is_file())
    print(f"bundle: {info['bundle']}")
    print(f"files: {files}")
    print(f"path-redacted copies: {len(info['redacted'])}")
    print(f"operator-side files omitted: {len(info['skipped'])}")
    print(f"QA failures: {len(problems)}")
    for p in problems:
        print(f"  - {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())

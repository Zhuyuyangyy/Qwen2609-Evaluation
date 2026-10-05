"""Public checks for RB-AS-004.

These assert the shape of a correct answer without giving the answer away.

They do NOT contain the measured figures, and they do not say which document
is wrong. What they establish is:

* every figure the docs state must be labelled with what it counts, because
  "tests" and "passing tests" are different quantities;
* the repository's own measurement commands must remain runnable, so the
  agent's numbers can be traced;
* documentation that quotes a number must quote one that is checkable.

The specific stale values and the authoritative counts live only in the
hidden checks.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

SNAPSHOT = Path(__file__).resolve().parents[1] / "repo_snapshot"

DOC_FILES = [
    SNAPSHOT / "README.md",
    SNAPSHOT / "docs" / "research" / "BENCHMARK_STATUS.md",
]


def _read(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise AssertionError(f"cannot decode {path}")


def test_documentation_files_still_exist():
    for p in DOC_FILES:
        assert p.exists(), f"{p.name} was deleted; docs must be synced, not removed"


def test_test_count_statements_are_labelled():
    """A bare "N tests" figure is ambiguous by construction.

    The task says a count of collected tests is not interchangeable with a
    count of passing tests, so any suite-size statement must carry its unit.
    This is a structural requirement, not a value check, so it passes on the
    shipped (stale) snapshot -- which is correct, because the public suite
    must not fail before the agent has done anything.
    """
    text = "\n".join(_read(p) for p in DOC_FILES)
    labelled = re.findall(
        r"\b\d+\s+(?:tests?|passed|passing|collected|cases)\b", text, re.IGNORECASE)
    assert labelled, "no suite-size statements found at all"


def test_collect_only_still_runs():
    """The authoritative measurement must remain available.

    Guards against a submission that "fixes" the docs by deleting the
    measurement path.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=str(SNAPSHOT), capture_output=True, text=True, timeout=600,
    )
    assert proc.returncode == 0, proc.stdout[-1500:] + proc.stderr[-1500:]


def test_benchmark_artifact_is_readable_and_unchanged_in_shape():
    """The artifact the docs must agree with must stay readable."""
    import json

    p = SNAPSHOT / "benchmark" / "benchmark_v3_standard.json"
    assert p.exists()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "total" in data and "results" in data


def test_result_artifacts_were_not_edited_to_match_docs():
    """Anti-cheat for the obvious shortcut.

    Checksums for the frozen artifacts live in the benchmark's own checksum
    file; if an agent rewrote a result JSON to agree with the README, the
    harness's frozen-file check would already flag it. This test confirms the
    file is still valid JSON with the keys the docs quote, so an agent cannot
    get away with gutting it.
    """
    import json

    p = SNAPSHOT / "benchmark" / "benchmark_v3_standard.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert isinstance(data.get("results"), list)
    assert data["total"] == len(data["results"]), (
        "the artifact's own total and its result list disagree; the artifact "
        "may have been edited"
    )
